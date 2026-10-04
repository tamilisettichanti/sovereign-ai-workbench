"""Agent orchestration.

run_task() routes a request to a model and then runs one of four flows, yielding events
that the web UI shows live:

  chat    - a direct answer from the small fast model
  vision  - OCR + the vision model on an attached image
  code    - the coding model writes a script, the sandbox runs it, errors are fed back
  agent   - plan, then loop: call a tool, read the result, decide the next step.
            When a deliverable is requested, the model writes the document as its final
            reply and the orchestrator saves it as Word / Excel / PowerPoint.

Event types: route, plan, step, token, answer_reset, file, error, done
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path

from . import audit, llm, registry, router, rules, tools
from .config import (AGENT_NUM_CTX, IMAGE_EXTS, MAX_AGENT_STEPS, MAX_CODE_ATTEMPTS, OUTPUTS)
from .tools import vision
from .tools.files import resolve_input
from .tools.ocr import extract_labels, extract_text

_CODE_BLOCK = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.S)


def run_task(message, attachments=(), user="system", force=None):
    started = time.time()
    attachments = list(attachments or [])
    decision = router.route(message, attachments, user=user, force=force)
    yield {"type": "route", **decision}
    if not decision["model"]:
        yield {"type": "error", "message": f"No installed and enabled model can handle a "
                                           f"'{decision['capability']}' task. Check the Models page."}
        yield {"type": "done", "duration_s": 0, "status": "failed"}
        return

    waited = llm.is_busy()
    if waited:
        yield _step(-1, "Another task is running. Waiting in the queue", "running")
    flow = {"chat": _chat, "vision": _vision, "code": _code, "agent": _agent}[decision["task"]]
    status = "completed"
    llm.acquire_task()
    try:
        if waited:
            yield _step(-1, "Queue cleared. Starting", "done")
        started = time.time()
        audit.log("task_start", user=user, task=decision["task"], model=decision["model"],
                  request=message[:200], attachments=attachments)
        yield from flow(message, attachments, decision, user)
    except llm.LLMError as e:
        status = "failed"
        yield {"type": "error", "message": str(e)}
    except Exception as e:  # keep the stream alive and show what went wrong
        status = "failed"
        yield {"type": "error", "message": f"{type(e).__name__}: {e}"}
    finally:
        llm.release_task()  # also runs if the browser disconnects mid-task
    duration = round(time.time() - started, 1)
    audit.log("task_done", user=user, task=decision["task"], model=decision["model"],
              request=message[:200], status=status, duration_s=duration)
    yield {"type": "done", "duration_s": duration, "status": status}


def _step(n, title, status, detail="", tool=None):
    return {"type": "step", "id": n, "title": title, "status": status, "detail": detail, "tool": tool}


def _stream(model, messages, user, purpose, **kw):
    """Forward tokens as events; the final assistant message is returned via StopIteration."""
    final = None
    for ev in llm.chat_stream(model, messages, user=user, purpose=purpose, **kw):
        if "token" in ev:
            yield {"type": "token", "text": ev["token"]}
        elif ev.get("done"):
            final = ev
    return final


# --------------------------------------------------------------------------- chat

def _chat(message, attachments, decision, user):
    yield _step(1, f"Answering with {decision['model_label']}", "running")
    messages = [
        {"role": "system", "content": "You are the Sovereign AI Workbench assistant, running fully "
                                      "on-premise for an industrial organisation. Answer clearly and briefly."},
        {"role": "user", "content": message},
    ]
    final = yield from _stream(decision["model"], messages, user, "chat")
    yield _step(1, f"Answered with {decision['model_label']}", "done", f"{final['duration_s']} s")


# ------------------------------------------------------------------------- vision

def _vision(message, attachments, decision, user):
    images = [a for a in attachments if Path(a).suffix.lower() in IMAGE_EXTS]
    n = 0
    for i, name in enumerate(images):
        path = resolve_input(name)
        n += 1
        yield _step(n, f"Reading text in {path.name} with on-device OCR", "running", tool="read_document")
        try:
            ocr_text = extract_text(path)["text"]
            labels = extract_labels(path)
        except Exception:
            ocr_text, labels = "", {"pairs": [], "tags": []}
        audit.log("tool_call", user=user, tool="read_document", ok=True, args={"path": path.name})
        found = "; ".join(f"{t} = {name}" for t, name in labels["pairs"])
        yield _step(n, f"OCR on {path.name}", "done",
                    f"{len(ocr_text)} characters of text, {len(labels['tags'])} tags"
                    + (f". Identified: {found}" if found else ""), tool="read_document")
        n += 1
        yield _step(n, f"Analysing {path.name} with {decision['model_label']}", "running",
                    tool="describe_image")
        if i:
            yield {"type": "token", "text": f"\n\n**{path.name}**\n\n"}
        final = yield from _stream(decision["model"], vision.vision_messages(path, message, ocr_text, labels),
                                   user, "vision")
        yield _step(n, f"Image analysed by {decision['model_label']}", "done", f"{final['duration_s']} s",
                    tool="describe_image")


# --------------------------------------------------------------------------- code

def _extract_code(text):
    blocks = _CODE_BLOCK.findall(text)
    return max(blocks, key=len).strip() if blocks else None


def _code(message, attachments, decision, user):
    messages = [
        {"role": "system", "content":
            "You are a careful Python engineer. Write one complete, self-contained Python script that "
            "solves the task. End the script with a few test cases that use assert and print the "
            "results, so that running it proves it works. Do not use input(), network access or "
            "external files. Reply with a one or two sentence explanation followed by exactly one "
            "```python code block."},
        {"role": "user", "content": message},
    ]
    n = 0
    for attempt in range(1, MAX_CODE_ATTEMPTS + 1):
        n += 1
        title = "Writing code" if attempt == 1 else f"Fixing the error (attempt {attempt})"
        yield _step(n, f"{title} with {decision['model_label']}", "running")
        if attempt > 1:
            yield {"type": "token", "text": f"\n\n---\n**Attempt {attempt}: corrected code**\n\n"}
        final = yield from _stream(decision["model"], messages, user, "code generation")
        reply = final["message"]["content"]
        yield _step(n, f"{title} with {decision['model_label']}", "done", f"{final['duration_s']} s")

        code = _extract_code(reply)
        if not code:
            return  # the answer was an explanation, nothing to run

        n += 1
        yield _step(n, "Running the code in the sandbox", "running", tool="run_python")
        result = tools.execute("run_python", {"code": code}, {"user": user})
        if result["ok"]:
            name = f"solution_{datetime.now():%Y%m%d_%H%M%S}.py"
            (OUTPUTS / name).write_text(code, encoding="utf-8")
            yield _step(n, "Sandbox run passed: code verified", "done", result["output"], tool="run_python")
            yield {"type": "token", "text": "\n\n**Verified in the sandbox**\n\n```\n" + result["output"] + "\n```\n"}
            yield {"type": "file", "name": name}
            return
        yield _step(n, "Sandbox run failed", "failed", result["output"], tool="run_python")
        messages += [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": "Running that script in the sandbox failed:\n\n"
                                        f"{result['output']}\n\nFix the problem and reply with the "
                                        "full corrected script in one ```python block."},
        ]
    yield {"type": "token", "text": f"\n\nThe code still failed after {MAX_CODE_ATTEMPTS} attempts. "
                                    "The last error is shown in the steps."}


# -------------------------------------------------------------------------- agent

# The model calls tools to gather information. File generation is done by the
# orchestrator from the model's final reply: a small model writes a document far more
# reliably as plain text than inside the JSON of a tool call.

# deliverable -> (tool, extension, how the model must write its final reply)
DELIVERABLES = {
    "excel": ("create_excel", ".xlsx",
              "Your final reply must be ONLY a markdown table (a header row, then one row per item). "
              "It will be saved as an Excel file."),
    "powerpoint": ("create_presentation", ".pptx",
                   "Your final reply must be ONLY the slides: a '## ' line with the slide title, then 3 or 4 "
                   "short '- ' bullet lines. Exactly 4 slides, under 150 words in total. It will be saved "
                   "as a PowerPoint file."),
    "word": ("create_word", ".docx",
             "Your final reply must be ONLY the document itself in markdown: '## ' section headings, "
             "'- ' bullets, and one markdown table for the findings. Use the sections, in the order, that "
             "the organisation's format document lists, and name the approving authority that the format "
             "document gives for the cost. Do not copy signature blocks or stamps from the source. Under "
             "300 words. No preamble and no closing remarks. It will be saved as a Word file."),
}
_DELIVERABLE_PATTERNS = [
    ("excel", re.compile(r"\b(excel|xlsx|spreadsheet)\b", re.I)),
    ("powerpoint", re.compile(r"\b(ppt|pptx|powerpoint|presentation|slides)\b", re.I)),
    ("word", re.compile(r"\b(word|docx|approval note)\b|"
                        r"\b(create|generate|draft|prepare|write|make)\b.{0,40}\b(note|report|memo|file|document)\b", re.I)),
]

_VISUAL = re.compile(r"\b(drawing|diagram|p&id|pid|photo|photograph|picture|sketch|image)\b", re.I)
_CALC = re.compile(r"\b(calculat\w+|compute|average|total|sum|convert|rate|remaining life)\b", re.I)
MAX_GATHER_STEPS = 4      # tool calls allowed before the model must write its answer

_AGENT_SYSTEM = """You are the Sovereign AI Workbench agent. You run fully on-premise for an industrial \
organisation and complete tasks by calling tools, one step at a time.

Rules:
- Read attached documents and scanned files with read_document (OCR is automatic). This \
includes scanned reports saved as images.
{vision_rule}
- Before drafting an official note or stating a limit, call search_knowledge_base to find the \
organisation's own SOPs, limits and document formats, and follow them.
- When a document gives a measured value and a limit, compare them and write the arithmetic \
out, for example "9.2 - 8.5 = 0.7 mm". Never make up a measured value: if the user only asks \
what a limit or procedure is, just state it.
- If a tool result contains a "Range check computed by the system", it is exact: follow it.
- For an engineering calculation, first call search_knowledge_base for the organisation's \
formula, then use run_python with print() and report the numbers it printed.
- Call one tool at a time, never the same call twice. Do not write explanations between tool calls.
- As soon as you have the facts you need, stop calling tools and write the final reply.
- Use only facts and numbers from the documents and tool results. Never invent facts.
- {final_rule}

Today's date: {date}
Attached files: {files}"""

_PLAN_SYSTEM = """You plan work for an on-premise AI agent with these tools: read_document (file reading \
with OCR), {vision_tool}search_knowledge_base (internal SOPs and manuals), {calc_tool}and file \
generation (Word, Excel, PowerPoint).
Write the plan for the user's task as 3 or 4 short numbered steps, one line each. Use only the tools \
the task really needs. Output only the numbered steps."""


def _deliverable(message):
    for kind, pattern in _DELIVERABLE_PATTERNS:
        if pattern.search(message):
            return kind
    return None


def _parse_plan(text):
    steps = []
    for line in text.splitlines():
        m = re.match(r"^\s*(?:\d+[.)]|[-*])\s+(.*\S)", line)
        if m:
            steps.append(m.group(1).replace("**", ""))
    return steps[:5]


def _json_objects(text):
    """Every balanced {...} in the text that parses as JSON."""
    found, depth, start = [], 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    found.append(json.loads(text[start:i + 1]))
                except ValueError:
                    pass
    return found


def _tool_calls(message):
    """Tool calls from the model, including ones it wrote as plain JSON text."""
    calls = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function", {})
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {}
        calls.append({"name": fn.get("name", ""), "arguments": args})
    if calls:
        return calls, False
    for obj in _json_objects(message.get("content") or ""):
        if isinstance(obj, dict) and obj.get("name") in tools.TOOLS:
            args = obj.get("arguments", obj.get("parameters", {}))
            calls.append({"name": obj["name"], "arguments": args if isinstance(args, dict) else {}})
    return calls, bool(calls)


def _describe_call(name, args):
    if name in ("read_document", "describe_image"):
        return f"{tools.label(name)}: {args.get('path', '')}"
    if name == "search_knowledge_base":
        return f"Knowledge base search: \"{args.get('query', '')}\""
    if name == "run_python":
        return "Running a calculation in the code sandbox"
    if name.startswith("create_"):
        return f"{tools.label(name)}: {args.get('filename', '')}"
    return tools.label(name)


def _file_call(kind, request, content):
    """The create_ tool call that saves the model's final reply as the requested file."""
    tool, ext, _ = DELIVERABLES[kind]
    low = request.lower()
    if "approval note" in low:
        title, stem = "Approval Note", "approval_note"
    elif "report" in low and kind == "word":
        title, stem = "Report", "report"
    else:
        title, stem = {"word": ("Document", "document"), "excel": ("Findings", "findings"),
                       "powerpoint": ("Presentation", "presentation")}[kind]
    heading = re.search(r"^\s*#{1,2}\s+(.{4,90})$", content, re.M)
    if heading and kind == "powerpoint":
        title = heading.group(1).strip(" *#")
    args = {"filename": f"{stem}_{datetime.now():%H%M%S}{ext}", "title": title, "content": content}
    if kind == "excel":
        table = "\n".join(ln for ln in content.splitlines() if ln.strip().startswith("|"))
        args["content"] = table or content
    return tool, args


def _agent(message, attachments, decision, user):
    model = decision["model"]
    files_text = ", ".join(attachments) if attachments else "none"
    task_text = message + (f"\n\nAttached files: {files_text}" if attachments else "")
    kind = _deliverable(message)
    # Offer only the tools this task can need: fewer choices keep a small model on track.
    has_vision = registry.pick("vision") is not None and bool(_VISUAL.search(message))
    wants_calc = bool(_CALC.search(message))
    offered = ["read_document", "search_knowledge_base"]
    if has_vision:
        offered.append("describe_image")
    if wants_calc:
        offered.append("run_python")
    if not attachments:
        offered.append("list_files")
    schemas = [tools.TOOLS[t]["schema"] for t in offered]

    # 1. plan
    yield _step(0, "Planning the task", "running")
    plan_system = _PLAN_SYSTEM.format(
        vision_tool="describe_image (vision model, for drawings and photographs only), " if has_vision else "",
        calc_tool="run_python (sandbox for calculations), " if wants_calc else "")
    plan_msg = llm.chat(model, [{"role": "system", "content": plan_system},
                                {"role": "user", "content": task_text}],
                        user=user, purpose="agent plan", num_predict=110)
    plan = _parse_plan(plan_msg["content"])
    yield {"type": "plan", "steps": plan}
    yield _step(0, "Plan ready", "done", f"{len(plan)} steps")

    # 2. act
    system = _AGENT_SYSTEM.format(
        date=f"{datetime.now():%d %B %Y}", files=files_text,
        vision_rule=("- Use describe_image only for drawings, diagrams and photographs, never for pages of text."
                     if has_vision else "- No vision model is available; rely on read_document."),
        final_rule=(DELIVERABLES[kind][2] if kind else
                    "Your final reply is a concise answer that names the sources you used."))
    messages = [{"role": "system", "content": system}, {"role": "user", "content": task_text}]
    ctx = {"user": user}
    sources, n, nudges = [], 0, 0

    def run_tool(name, args):
        """Execute one tool and report it as a step. Returns the tool result."""
        nonlocal n
        n += 1
        title = _describe_call(name, args)
        yield _step(n, title, "running", tool=name)
        result = tools.execute(name, args, ctx)
        detail = result["output"] if len(result["output"]) < 600 else result["output"][:600] + " ..."
        yield _step(n, title, "done" if result["ok"] else "failed", detail, tool=name)
        if result.get("file"):
            yield {"type": "file", "name": result["file"]}
        for s in result.get("sources", []):
            if s["source"] not in sources:
                sources.append(s["source"])
        return result

    final_rule = DELIVERABLES[kind][2] if kind else "Write the final answer now and name the sources you used."
    seen, read_text = set(), []
    # finalize: 0 = gathering; 1 = told to write the answer (tools still listed, so Ollama's
    # prompt cache is reused); 2 = tools withdrawn because it called one anyway. Withdrawing
    # tools changes the prompt prefix and costs a full re-read, so it is the last resort.
    finalize = 0

    for _ in range(MAX_AGENT_STEPS):
        final = yield from _stream(model, messages, user, "agent step",
                                   tools=None if finalize == 2 else schemas, num_ctx=AGENT_NUM_CTX)
        reply = final["message"]
        calls, from_text = ([], False) if finalize == 2 else _tool_calls(reply)

        if calls:
            yield {"type": "answer_reset"}  # anything streamed so far was working text, not the answer
            messages.append({"role": "assistant", "content": reply.get("content", "")} if from_text else reply)
            was_finalizing, refused = finalize >= 1, False
            for call in calls:
                signature = call["name"] + json.dumps(call["arguments"], sort_keys=True, default=str)
                if was_finalizing or signature in seen or call["name"] not in offered:
                    refused = True  # repeating itself, or reaching for a tool it was not given
                    messages.append({"role": "tool", "tool_name": call["name"],
                                     "content": "Not run: you already have what you need. Write the final reply."})
                    continue
                seen.add(signature)
                result = yield from run_tool(call["name"], call["arguments"])
                content = result["output"]
                if call["name"] == "read_document" and result["ok"]:
                    read_text.append(content)
                elif call["name"] == "search_knowledge_base" and result["ok"]:
                    # Numeric limits are checked in code: the model misjudges "is 4.8 above 5?".
                    notes = rules.range_notes(content, rules.values_in("\n".join(read_text) + "\n" + message))
                    if notes:
                        content += "\n\n" + notes
                        yield _step(n, _describe_call(call["name"], call["arguments"]), "done",
                                    result["output"][:400] + " ...\n\n" + notes, tool=call["name"])
                messages.append({"role": "tool", "tool_name": call["name"], "content": content})
            if was_finalizing:
                finalize = 2
            elif refused or n >= MAX_GATHER_STEPS:
                finalize = 1
                messages.append({"role": "user", "content": "You now have everything you need. " + final_rule})
            continue

        content = (reply.get("content") or "").strip()
        problem = None
        if attachments and n == 0:
            problem = "You have not read the attached file yet. Call read_document on it first."
        elif len(content) < 40:
            problem = "Your reply was empty. " + (DELIVERABLES[kind][2] if kind else "Write the answer now.")
        if problem and nudges < 2:
            nudges += 1
            yield {"type": "answer_reset"}
            messages += [{"role": "assistant", "content": content}, {"role": "user", "content": problem}]
            continue

        # The streamed text is the final answer. Save it if a deliverable was requested.
        if kind and content:
            result = yield from run_tool(*_file_call(kind, message, content))
            note = (f"Saved as **{result['file']}** (see the Output panel)." if result["ok"]
                    else f"The file could not be saved: {result['output']}")
            if sources:
                note += " Grounded in: " + ", ".join(sources) + "."
            yield {"type": "token", "text": "\n\n---\n" + note}
        return

    yield {"type": "token", "text": f"\n\nStopped after {MAX_AGENT_STEPS} steps without a final answer."}
