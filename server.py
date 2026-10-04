"""Sovereign AI Workbench - web server.

Serves the website and its API on http://127.0.0.1:8000 (this machine only).
Start it with run.bat, or:  .venv\\Scripts\\python server.py
"""
import json
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

import uvicorn
from fastapi import Body, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from workbench import agent, audit, auth, config, llm, netguard, rag, registry, router, tools
from workbench.tools import office
from workbench.tools.ocr import extract_text

netguard.install()
auth.ensure_users()

app = FastAPI(title="Sovereign AI Workbench", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=config.WEB_DIR), name="static")

AREAS = {"uploads": config.UPLOADS, "samples": config.SAMPLES_DIR,
         "outputs": config.OUTPUTS, "kb": config.KB_DIR}


# ------------------------------------------------------------------ helpers

def current_user(request: Request):
    user = auth.session(request.cookies.get("sid"))
    if not user:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user


# Long tasks run in their own thread and record their events here, so a task does not
# depend on the browser connection that started it. If the stream drops (a task can take
# several minutes on this CPU), the page reconnects to /api/task/<id> and carries on from
# the event it had reached.
TASKS = {}
_tasks_lock = threading.Lock()


def _start_task(events):
    task_id = secrets.token_hex(8)
    task = {"events": [], "done": False}
    with _tasks_lock:
        for old in list(TASKS)[:-20]:      # keep only the most recent tasks
            if TASKS[old]["done"]:
                del TASKS[old]
        TASKS[task_id] = task

    def run():
        try:
            for ev in events:
                task["events"].append(ev)
        except Exception as e:
            task["events"].append({"type": "error", "message": f"{type(e).__name__}: {e}"})
            task["events"].append({"type": "done", "status": "failed"})
        finally:
            task["done"] = True

    threading.Thread(target=run, daemon=True).start()
    return task_id


def _follow(task_id, start=0):
    """Stream a task's events from position `start`, with a heartbeat while it is quiet."""
    task = TASKS.get(task_id)

    def body():
        yield f"data: {json.dumps({'type': 'task', 'id': task_id})}\n\n"
        i, quiet = start, 0.0
        while True:
            if i < len(task["events"]):
                yield f"data: {json.dumps(task['events'][i], default=str)}\n\n"
                i, quiet = i + 1, 0.0
            elif task["done"]:
                break
            else:
                time.sleep(0.2)
                quiet += 0.2
                if quiet >= 10:            # the model is reading a long prompt: keep the line alive
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
                    quiet = 0.0
        yield f"data: {json.dumps({'type': 'end'})}\n\n"

    return StreamingResponse(body(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def sse(events):
    """Run a generator of event dicts as a background task and stream it to the browser."""
    return _follow(_start_task(events))


def clean_name(name):
    name = Path(name or "file").name
    return "".join(c if c.isalnum() or c in "-_. ()" else "_" for c in name).strip() or "file"


def file_info(path, area):
    st = path.stat()
    return {"name": path.name, "area": area, "size_kb": round(st.st_size / 1024, 1),
            "ext": path.suffix.lower().lstrip("."),
            "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            "is_image": path.suffix.lower() in config.IMAGE_EXTS}


def list_area(area):
    files = [f for f in AREAS[area].iterdir() if f.is_file()]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return [file_info(f, area) for f in files]


def area_file(area, name):
    if area not in AREAS:
        raise HTTPException(404, "Unknown area")
    path = AREAS[area] / Path(name).name
    if not path.is_file():
        raise HTTPException(404, "File not found")
    return path


# -------------------------------------------------------------------- pages

@app.get("/")
def root(request: Request):
    return RedirectResponse("/app" if auth.session(request.cookies.get("sid")) else "/login")


@app.get("/login")
def login_page():
    return FileResponse(config.WEB_DIR / "login.html")


@app.get("/app")
def app_page(request: Request):
    if not auth.session(request.cookies.get("sid")):
        return RedirectResponse("/login")
    return FileResponse(config.WEB_DIR / "app.html", headers={"Cache-Control": "no-store"})


# --------------------------------------------------------------------- auth

@app.post("/api/login")
def api_login(data: dict = Body(...)):
    token, user = auth.login(data.get("username"), data.get("password"))
    if not token:
        return JSONResponse({"error": "Wrong username or password"}, status_code=401)
    resp = JSONResponse({"user": user})
    resp.set_cookie("sid", token, httponly=True, samesite="strict")
    return resp


@app.post("/api/logout")
def api_logout(request: Request):
    auth.logout(request.cookies.get("sid"))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("sid")
    return resp


@app.get("/api/me")
def api_me(user=Depends(current_user)):
    return user


# ---------------------------------------------------------------- dashboard

_tesseract_version = None


def tesseract_version():
    global _tesseract_version
    if _tesseract_version is None:
        try:
            import pytesseract
            _tesseract_version = str(pytesseract.get_tesseract_version()).split()[0]
        except Exception:
            _tesseract_version = ""
    return _tesseract_version


@app.get("/api/dashboard")
def api_dashboard(user=Depends(current_user)):
    models = registry.models()
    active = [m for m in models if m["installed"] and m["enabled"]]
    kb = rag.stats()
    net = netguard.snapshot()
    tasks = audit.read(limit=100000, kind=("task_done",))
    up = llm.is_up()
    activity = audit.read(limit=8, kind=("task_done", "kb_ingest", "kb_delete"))
    return {
        "cards": {
            "tasks": len(tasks),
            "kb_documents": kb["documents"],
            "models_active": len(active),
            "files_generated": len(list_area("outputs")),
        },
        "activity": activity,
        "status": [
            {"name": "LLM Server", "detail": f"Ollama {llm.version()} on 127.0.0.1:11434" if up else "Ollama is not running",
             "ok": up},
            {"name": "Local Models", "detail": ", ".join(m["label"] for m in active) or "none available", "ok": bool(active)},
            {"name": "Vector Database", "detail": f"{kb['chunks']} passages from {kb['documents']} documents", "ok": True},
            {"name": "OCR Engine", "detail": f"Tesseract {tesseract_version()}" if tesseract_version() else "Tesseract not found",
             "ok": bool(tesseract_version())},
            {"name": "Code Sandbox", "detail": "Isolated process, no network", "ok": True},
            {"name": "File Generation", "detail": "DOCX, PPTX, XLSX", "ok": True},
            {"name": "Network Monitor", "detail": f"{net['external_count']} external connections", "ok": net["external_count"] == 0},
            {"name": "Audit Logger", "detail": "Logging enabled", "ok": True},
        ],
    }


# -------------------------------------------------------------------- files

@app.post("/api/upload")
async def api_upload(files: list[UploadFile] = File(...), user=Depends(current_user)):
    saved = []
    for f in files:
        name = clean_name(f.filename)
        (config.UPLOADS / name).write_bytes(await f.read())
        saved.append(name)
        audit.log("upload", user=user["username"], file=name)
    return {"files": saved}


@app.get("/api/files")
def api_files(user=Depends(current_user)):
    return {area: list_area(area) for area in ("uploads", "samples", "outputs")}


@app.get("/api/file/{area}/{name}")
def api_file(area: str, name: str, download: int = 0, user=Depends(current_user)):
    path = area_file(area, name)
    if download:
        audit.log("download", user=user["username"], file=path.name)
        return FileResponse(path, filename=path.name)
    return FileResponse(path)


@app.delete("/api/file/{area}/{name}")
def api_file_delete(area: str, name: str, user=Depends(current_user)):
    if area not in ("uploads", "outputs"):
        raise HTTPException(400, "Only uploaded and generated files can be removed here")
    area_file(area, name).unlink()
    audit.log("file_delete", user=user["username"], file=name, area=area)
    return {"ok": True}


# ---------------------------------------------------------------- workbench

@app.post("/api/chat")
def api_chat(data: dict = Body(...), user=Depends(current_user)):
    message = (data.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "Message is empty")
    return sse(agent.run_task(message, data.get("attachments") or [], user=user["username"]))


@app.get("/api/task/{task_id}")
def api_task(task_id: str, start: int = 0, user=Depends(current_user)):
    """Rejoin a running (or finished) task after the first stream was interrupted."""
    if task_id not in TASKS:
        raise HTTPException(404, "Task not found. It may have been started before a server restart.")
    return _follow(task_id, max(0, start))


# ---------------------------------------------------------------- documents

def _process_document(name, save_kb, username):
    path = tools.files.resolve_input(name)
    yield {"type": "stage", "name": "upload", "status": "done",
           "detail": f"{max(1, round(path.stat().st_size / 1024))} KB"}

    yield {"type": "stage", "name": "ocr", "status": "running"}
    result = extract_text(path)
    audit.log("tool_call", user=username, tool="read_document", ok=bool(result["text"]), args={"path": path.name})
    yield {"type": "stage", "name": "ocr", "status": "done",
           "detail": f"{result['method']}, {result['pages']} page(s), {len(result['text'])} characters"}
    yield {"type": "text", "text": result["text"], "method": result["method"], "pages": result["pages"]}
    if not result["text"]:
        yield {"type": "error", "message": "No readable text was found in this file."}
        yield {"type": "done", "status": "failed"}
        return

    model = registry.pick("tools") or registry.pick("fast")
    yield {"type": "stage", "name": "understand", "status": "running", "detail": model["label"] if model else ""}
    if model:
        messages = [
            {"role": "system", "content":
                "You analyse industrial documents. Reply with three short sections using these exact "
                "headings: 'Summary' (2-3 sentences), 'Key Information' (bullet points with the "
                "important values, tags, dates and names), 'Actions Required' (bullet points). "
                "Use only what is in the document. Report values as written; do not say whether a "
                "value is acceptable or within limits unless the document itself says so."},
            {"role": "user", "content": f"Document: {path.name}\n\n{result['text'][:6000]}"},
        ]
        llm.acquire_task()  # waits here if another AI task is running
        try:
            for ev in llm.chat_stream(model["name"], messages, user=username, purpose="document summary"):
                if "token" in ev:
                    yield {"type": "token", "text": ev["token"]}
        finally:
            llm.release_task()
    yield {"type": "stage", "name": "understand", "status": "done", "detail": model["label"] if model else "no model"}

    if save_kb:
        yield {"type": "stage", "name": "kb", "status": "running"}
        r = rag.ingest_file(path, user=username)
        yield {"type": "stage", "name": "kb", "status": "done", "detail": f"{r['chunks']} passages indexed"}
    else:
        yield {"type": "stage", "name": "kb", "status": "skipped", "detail": "not requested"}
    yield {"type": "done", "status": "completed"}


@app.post("/api/documents/process")
def api_documents_process(data: dict = Body(...), user=Depends(current_user)):
    return sse(_process_document(data.get("name", ""), bool(data.get("save_kb")), user["username"]))


# --------------------------------------------------------------- multimodal

@app.post("/api/vision/analyze")
def api_vision_analyze(data: dict = Body(...), user=Depends(current_user)):
    question = (data.get("question") or "").strip() or (
        "Describe what this image shows. List every piece of equipment and instrument with its tag, "
        "explain how they are connected, and note any other key information.")
    return sse(agent.run_task(question, [data.get("name", "")], user=user["username"], force="vision"))


@app.post("/api/vision/report")
def api_vision_report(data: dict = Body(...), user=Depends(current_user)):
    name = Path(data.get("name", "image")).stem
    result = tools.execute("create_word", {
        "filename": f"image_analysis_{name}.docx",
        "title": f"Image Analysis Report: {data.get('name', '')}",
        "content": f"## Source\n{data.get('name', '')}\n\n## Analysis\n{data.get('analysis', '')}",
    }, {"user": user["username"]})
    if not result["ok"]:
        raise HTTPException(400, result["output"])
    return {"file": result["file"]}


# ----------------------------------------------------------- knowledge base

@app.get("/api/kb/documents")
def api_kb_documents(user=Depends(current_user)):
    return {"documents": rag.list_documents(), "stats": rag.stats()}


@app.post("/api/kb/upload")
async def api_kb_upload(files: list[UploadFile] = File(...), user=Depends(current_user)):
    results = []
    for f in files:
        path = config.KB_DIR / clean_name(f.filename)
        path.write_bytes(await f.read())
        try:
            results.append(rag.ingest_file(path, user=user["username"]))
        except Exception as e:
            path.unlink(missing_ok=True)
            results.append({"source": path.name, "error": str(e)})
    return {"results": results}


@app.post("/api/kb/add")
def api_kb_add(data: dict = Body(...), user=Depends(current_user)):
    path = tools.files.resolve_input(data.get("name", ""))
    return rag.ingest_file(path, user=user["username"])


@app.delete("/api/kb/documents/{source}")
def api_kb_delete(source: str, user=Depends(current_user)):
    rag.delete_document(source, user=user["username"])
    return {"ok": True}


@app.post("/api/kb/reindex")
def api_kb_reindex(user=Depends(current_user)):
    return {"results": rag.ingest_folder(user=user["username"])}


@app.get("/api/kb/search")
def api_kb_search(q: str, user=Depends(current_user)):
    return {"hits": rag.search(q, k=8, user=user["username"])}


@app.post("/api/kb/ask")
def api_kb_ask(data: dict = Body(...), user=Depends(current_user)):
    return sse(rag.answer_stream(data.get("query", ""), user=user["username"]))


# ------------------------------------------------------------------- models

@app.get("/api/models")
def api_models(user=Depends(current_user)):
    return {"models": registry.models(), "fallbacks": registry.fallbacks(),
            "task_capability": router.TASK_CAPABILITY, "task_label": router.TASK_LABEL}


@app.post("/api/models/toggle")
def api_models_toggle(data: dict = Body(...), user=Depends(current_user)):
    registry.set_enabled(data["name"], data["enabled"])
    audit.log("model_toggle", user=user["username"], model=data["name"], enabled=bool(data["enabled"]))
    return {"models": registry.models()}


@app.post("/api/route/test")
def api_route_test(data: dict = Body(...), user=Depends(current_user)):
    attachments = data.get("attachments") or []
    return router.route(data.get("message", ""), attachments, user=user["username"])


@app.get("/api/routing")
def api_routing(user=Depends(current_user)):
    return {"activity": audit.read(limit=15, kind=("route",))}


# -------------------------------------------------------- audit and network

@app.get("/api/audit")
def api_audit(limit: int = 300, kind: str = "", user=Depends(current_user)):
    kinds = tuple(k for k in kind.split(",") if k) or None
    return {"records": audit.read(limit=limit, kind=kinds)}


@app.get("/api/network")
def api_network(user=Depends(current_user)):
    snap = netguard.snapshot()
    calls = audit.read(limit=100000, kind=("model_call",))
    snap["model_calls"] = len(calls)
    snap["endpoints"] = sorted({c["endpoint"].split("/api")[0] for c in calls})
    return snap


@app.post("/api/network/selftest")
def api_network_selftest(user=Depends(current_user)):
    """Deliberately try to reach an outside address, to show the guard refusing it."""
    import requests
    audit.log("guard_selftest", user=user["username"], dest="example.com")
    try:
        requests.get("http://example.com", timeout=5)
        return {"blocked": False, "detail": "the request to example.com went through"}
    except Exception as e:
        return {"blocked": True, "detail": f"request to example.com refused ({type(e).__name__})"}


# ------------------------------------------------- reports, agents, settings

@app.get("/api/reports")
def api_reports(user=Depends(current_user)):
    return {"files": list_area("outputs")}


@app.get("/api/agents")
def api_agents(user=Depends(current_user)):
    return {
        "flows": [
            {"name": "Document Agent", "task": "agent", "capability": "tools",
             "description": "Plans the work, then reads documents, searches the knowledge base, runs "
                            "calculations and writes Word, Excel or PowerPoint deliverables.",
             "tools": list(tools.TOOLS)},
            {"name": "Coding Agent", "task": "code", "capability": "code",
             "description": "Writes Python, runs it in the sandbox, and fixes it if the run fails.",
             "tools": ["run_python"]},
            {"name": "Vision Agent", "task": "vision", "capability": "vision",
             "description": "Reads drawings, photographs and scans using OCR and the vision model.",
             "tools": ["read_document", "describe_image"]},
            {"name": "Chat Assistant", "task": "chat", "capability": "fast",
             "description": "Answers short general questions with the small fast model.", "tools": []},
        ],
        "tools": [{"name": n, "label": t["label"], "description": t["schema"]["function"]["description"]}
                  for n, t in tools.TOOLS.items()],
        "limits": {"max_agent_steps": config.MAX_AGENT_STEPS, "max_code_attempts": config.MAX_CODE_ATTEMPTS,
                   "sandbox_timeout_s": config.SANDBOX_TIMEOUT},
        "task_counts": _task_counts(),
    }


def _task_counts():
    counts = {}
    for r in audit.read(limit=100000, kind=("task_done",)):
        counts[r.get("task", "")] = counts.get(r.get("task", ""), 0) + 1
    return counts


@app.get("/api/settings")
def api_settings(user=Depends(current_user)):
    return {"settings": [
        {"group": "Network", "items": [
            ["Web server address", f"http://{config.SERVER_HOST}:{config.SERVER_PORT} (this machine only)"],
            ["Model server address", config.OLLAMA_URL],
            ["Outbound connections", "Refused unless the destination is this machine"],
            ["Library telemetry", "Disabled"]]},
        {"group": "Models", "items": [
            ["Embedding model", config.EMBED_MODEL],
            ["Context window", f"{config.NUM_CTX} tokens (agent: {config.AGENT_NUM_CTX})"],
            ["Model registry file", "workbench/models.yaml"]]},
        {"group": "Agent", "items": [
            ["Maximum steps per task", str(config.MAX_AGENT_STEPS)],
            ["Code fix attempts", str(config.MAX_CODE_ATTEMPTS)],
            ["Sandbox time limit", f"{config.SANDBOX_TIMEOUT} seconds"]]},
        {"group": "Knowledge base", "items": [
            ["Vector database", "ChromaDB, stored in data/chroma"],
            ["Chunk size / overlap", f"{config.CHUNK_SIZE} / {config.CHUNK_OVERLAP} characters"],
            ["Passages retrieved per question", str(config.TOP_K)]]},
        {"group": "Storage", "items": [
            ["Uploads", "workspace/uploads"], ["Generated files", "workspace/outputs"],
            ["Audit log", "logs/audit.jsonl"], ["User accounts", "data/users.json (hashed passwords)"]]},
    ]}


if __name__ == "__main__":
    print(f"\n  Sovereign AI Workbench  ->  http://{config.SERVER_HOST}:{config.SERVER_PORT}\n")
    uvicorn.run(app, host=config.SERVER_HOST, port=config.SERVER_PORT, log_level="warning")
