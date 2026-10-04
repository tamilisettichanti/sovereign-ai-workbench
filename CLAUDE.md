# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A final-year project for problem statement 26117 (`ProblemStatement.txt`): a self-hosted AI workbench where
nothing leaves the machine. It is demoed on one Windows laptop. The thing being judged is the sovereign
claim, so **no online model APIs, no CDN assets, no outbound calls of any kind**. All models run through
a local Ollama server.

## Commands

The venv is `.venv` (Python 3.10, created with `--system-site-packages`; chromadb, fastapi and others
come from the system install). There is no build step, linter or unit-test suite.

```
.venv\Scripts\python server.py                    # run the site on http://127.0.0.1:8000 (or run.bat)
.venv\Scripts\python scripts\smoke_test.py        # all five requirement checks, about 6 min
.venv\Scripts\python scripts\smoke_test.py agent  # one scenario: routing | agent | code | vision | audit
.venv\Scripts\python scripts\make_samples.py      # regenerate samples/ (scanned report, P&ID drawing)
.venv\Scripts\python scripts\ingest_kb.py         # re-index knowledge_base/ into data/chroma
```

The server does not auto-reload: restart it after any Python change. Files under `web/` are served
live. `.claude/launch.json` defines the `workbench` preview server. Demo sign-in accounts are seeded
from `config/demo_users.json` into `data/users.json` on first start.

Prerequisites outside the venv: Ollama running with `qwen2.5`, `qwen2.5-coder:3b`, `llava:7b`,
`phi3:mini` and `nomic-embed-text` pulled, and Tesseract OCR on PATH. A model that is not pulled shows
as "Not downloaded" and the router falls back per `fallbacks` in `models.yaml`.

Runtime state is generated and safe to delete to reset: `data/` (users, sessions, model on/off state,
Chroma index), `logs/audit.jsonl`, `workspace/`. After deleting `data/chroma`, run `ingest_kb.py`.
The folder is not a git repository. `README.md` holds the demo script and measured timings.

`smoke_test.py` calls the real models. Do not run it while the website is running a task (see the
memory constraint below); it is a separate process and does not share the server's task queue.

## Hardware constraints that shape the code

The laptop is CPU-only with 16 GB RAM (about 6 tokens/s generation, 20 tokens/s prompt reading for a
7B model). These were all learned from failures and should not be undone casually:

- **One large model in memory at a time.** `llm.make_room_for()` unloads other chat models before each
  call. Two 7B models loaded together caused swapping and a 20-minute step.
- **One AI task at a time.** `llm.acquire_task()` / `release_task()` is a global lock taken in
  `agent.run_task`, `rag.answer_stream` and the document summary in `server.py`. Any new code path that
  calls a chat model must take it too.
- **One context size.** `NUM_CTX` is used for every call; changing `num_ctx` between calls makes Ollama
  reload the model. Tool outputs are capped (`TOOL_OUTPUT_LIMIT`) to stay inside it.
- **The 7B model does not write long documents inside tool-call JSON.** It either writes them as chat
  text or emits a call Ollama cannot parse. So the agent only gathers with tools; the deliverable is
  the model's final reply, saved by the orchestrator (`agent._file_call`).
- **The agent loops if given the chance.** It is offered only the tools the request needs, repeated
  calls are refused, and after `MAX_GATHER_STEPS` it is told to write. Tools are only withdrawn from
  the request if it calls one anyway, because removing them changes the prompt prefix and forces a
  full prompt re-read (about 3 minutes).

- **The 7B model misjudges numeric limits** ("is 4.8 above 5?"). `rules.range_notes()` finds range
  rules in SOP text and evaluates them in Python; the result is appended to the knowledge-base context
  (`rag.answer_stream`) and to `search_knowledge_base` tool results in the agent. Extend the patterns
  there rather than adding prompt instructions.
- **The vision model attaches tags to the wrong equipment.** `ocr.extract_labels()` pairs each tag with
  its nearest caption from OCR positions and `vision.vision_messages()` passes those pairs as facts.

## Architecture

```
web/ (plain HTML/CSS/JS, hash router, SSE)  ->  server.py (FastAPI, 127.0.0.1:8000)
                                                    -> workbench/  ->  Ollama (127.0.0.1:11434)
```

**Streaming and tasks.** Every streaming endpoint goes through `sse()` in `server.py`, which runs the
event generator in a background thread, records its events in `TASKS`, and streams them with a `task`
id first, `ping` heartbeats while quiet and a final `end`. `stream()` in `web/js/app.js` counts events
and, if the connection drops, rejoins via `GET /api/task/<id>?start=<n>`. A task therefore finishes
even if the browser goes away. (A stream dropped 5.5 minutes into a task during testing.)

**Request flow.** `POST /api/chat` streams dict events from `agent.run_task()`. `router.route()` classifies the request by rules (attachment types and keyword
regexes) into `chat | code | vision | agent`, maps that to a capability (`fast | code | vision | tools`),
and `registry.pick()` returns the first enabled, installed model in `workbench/models.yaml` with that
capability. Adding a model is one YAML entry; order in the file is priority.

**The four flows in `agent.py`** all yield the same event types (`route, plan, step, token,
answer_reset, file, error, done`), which `web/js/pages/workbench.js` renders:
- `_chat`: direct streamed answer.
- `_vision`: Tesseract OCR and `extract_tags()` feed tag spellings to the vision model as hints.
- `_code`: the coder model writes a script, `tools/sandbox.py` runs it, failures are fed back (up to 3 tries).
- `_agent`: a short plan call, then the tool loop described above.

**Tools** live in `workbench/tools/` and are registered with their JSON schemas in `tools/__init__.py`.
`tools.execute()` never raises; it returns `{"ok", "output", ...}` and writes an audit record. Tool file
access is confined by `tools/files.py::resolve_input` to uploads, outputs, samples and the knowledge base.
Office files are generated from markdown-style text (`tools/office.py`), not nested structures.

**RAG (`rag.py`).** Line-based chunks with overlap, embedded by `nomic-embed-text` (with
`search_document:` / `search_query:` prefixes), stored in ChromaDB at `data/chroma`. The agent's
`search_knowledge_base` tool returns the *whole* document when the best match is short
(`WHOLE_DOC_LIMIT`), because fragments of an SOP led the model to misapply limits. Within one task it
never returns the same document twice (`ctx["kb_given"]`), so a second search reaches a different SOP.

**Sovereignty.** `netguard.install()` (called at import in `server.py` and the scripts) wraps
`socket.connect` and `getaddrinfo` so non-loopback destinations are refused and logged.
`netguard.snapshot()` lists live sockets of this process and Ollama for the Audit Logs page. Every model
call, tool call and routing decision is appended to `logs/audit.jsonl` via `audit.log()`; several pages
(dashboard activity, routing activity, task counts) are read straight from that log.

**Front end.** `web/js/app.js` holds the shell: inline SVG icons, `api()`, `stream()` (SSE over fetch),
a small markdown renderer and the hash router. Each file in `web/js/pages/` registers
`Pages.<name> = {title, render(el), leave?}`. The router gives every visit a fresh container so a slow
page cannot overwrite the one now on screen. A new page needs a script tag in `web/app.html` and an
entry in `App.nav`.

## Conventions

- `user` (the signed-in username) is passed explicitly through agent, tool and LLM calls for the audit
  log; SSE generators run across threadpool threads, so context variables are not used.
- `samples/` and `knowledge_base/` content is synthetic demo data under a fictional "Coastal Refinery
  Unit" name. Keep it that way; do not present it as real organisational records.
- Small-model output is unreliable (arithmetic, applying thresholds, reading dense drawings). Prefer
  moving a decision into code or retrieval over adding more prompt instructions.
