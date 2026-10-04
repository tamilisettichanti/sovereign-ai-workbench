# Sovereign On-Premise Agentic AI Workbench

A self-hosted AI workbench for confidential industrial work (problem statement 26117, MRPL).
Every model runs on this laptop through Ollama. Nothing is sent to the internet.

## Start it

Double-click `run.bat`, or:

```
.venv\Scripts\python server.py
```

Then open http://127.0.0.1:8000 and sign in. The demo accounts are in
`config/demo_users.json`.

**Before the demo:** close other heavy apps (browsers with many tabs, IDEs). The laptop has
16 GB of RAM and a 7B model needs about 5 GB of it.

## What it shows

| Requirement in the problem statement | Where to show it |
|---|---|
| Model auto-selection across task types | Models page: "Test the Router". Also the "Routed to" badge on every answer |
| Agentic task end to end | AI Workbench: chip "Approval note from scanned report" |
| Coding task verified in a sandbox | AI Workbench: chip "Write and verify code" |
| Multimodal task | AI Workbench: chip "Explain this P&ID", or the Multimodal Analysis page |
| Proof of no external calls | Audit Logs page, then repeat any task with Wi-Fi switched off |
| Local knowledge base (RAG) | Knowledge Base page: "Ask AI from Knowledge Base" |
| Real deliverables | Reports page lists the generated Word / Excel / PowerPoint files |

## Demo script (about 12 minutes)

1. **Login and Dashboard.** Point out the live system status: Ollama, vector database, OCR, sandbox.
2. **Models page.** Four local models. Click the router examples and watch the highlighted path change.
   Switch one model off and show that routing falls back.
3. **AI Workbench, quick question** (chip "Quick question", about 25 s). Routed to Phi-3 Mini.
4. **AI Workbench, coding** (chip "Write and verify code", about 30 s). Routed to Qwen Coder; the code
   runs in the sandbox and the output is shown.
5. **AI Workbench, agent task** (chip "Approval note from scanned report", about 4 min). Start it, then
   explain the steps as they appear: plan, OCR of the scan, knowledge base search, Word file. Open the file.
6. **Multimodal Analysis** (about 2 min). Analyse the sample P&ID.
7. **Knowledge Base.** Ask "Who approves a repair costing Rs 4.8 lakh?" and show the cited sources.
8. **Audit Logs.** Zero external connections, every model call to 127.0.0.1, and "Test the outbound guard".
9. **Wi-Fi off.** Run the quick question again to show it still works.

## Timings on this laptop (CPU only)

| Task | Time |
|---|---|
| Quick question (Phi-3 Mini) | about 25 s |
| Code written and verified (Qwen Coder 3B) | about 25 s |
| Knowledge base "Ask AI" | about 15 to 45 s |
| Procedure question through the agent | about 1.5 min |
| Calculation (formula from the SOP, run in the sandbox) | about 2.5 min |
| P&ID analysis (LLaVA 7B) | about 2 min |
| Document page: extract and summarise | about 1.5 min |
| Scanned report to PowerPoint | about 2.5 to 3 min |
| Scanned report to Excel | about 3.5 min |
| Scanned report to approval note (Qwen 2.5 7B, 4 steps) | about 4 to 5 min |

Switching between the large models adds 10 to 15 s while the next one loads, because only one
large model is kept in memory at a time.

## How it is built

```
Browser (HTML/CSS/JS, all assets local)
   |  fetch + Server-Sent Events, 127.0.0.1:8000
FastAPI backend (server.py) -- auth -- audit log -- network guard
   |- router.py     picks a model per task from models.yaml
   |- agent.py      plan -> call tool -> read result -> repeat -> write deliverable
   |- tools/        OCR, vision, knowledge base search, Python sandbox, Word/Excel/PowerPoint
   |- rag.py        ChromaDB (folder on disk) + nomic-embed-text embeddings
Ollama, 127.0.0.1:11434 -> qwen2.5, qwen2.5-coder:3b, llava:7b, phi3:mini
```

| Folder / file | Purpose |
|---|---|
| `server.py` | Web server and API |
| `workbench/` | Backend logic (router, agent, tools, RAG, audit, network guard) |
| `workbench/models.yaml` | Model registry. Add a model here after `ollama pull` |
| `web/` | The website (no build step) |
| `knowledge_base/` | Documents indexed for RAG (sample SOPs) |
| `samples/` | Demo inputs: scanned inspection report, P&ID drawing |
| `workspace/outputs/` | Generated deliverables |
| `logs/audit.jsonl` | Audit trail |
| `scripts/` | `make_samples.py`, `ingest_kb.py`, `smoke_test.py` |

## Adding a new model

```
ollama pull <model-name>
```

Then add an entry to `workbench/models.yaml` with its capabilities (`tools`, `code`, `vision`,
`fast`). The router uses it without any code change.

## Checking it without the website

```
.venv\Scripts\python scripts\smoke_test.py
```

Runs routing, the agent task, the coding task, the vision task and the sovereignty checks,
and prints PASS or FAIL for each.

## Known limits

- CPU only, so answers take seconds to minutes. The problem statement allows a smaller model for the demo.
- 7B models make mistakes. Two known weaknesses are handled in code: numeric limits are checked by
  `workbench/rules.py`, and equipment tags on drawings are matched to their captions by OCR position.
  Wording and judgement in generated documents still vary from run to run and need human review.
- OCR reads printed text well. Handwriting is not read, and tags inside instrument circles on
  drawings are usually missed.
- The code sandbox is a restricted subprocess (no network, time limit, own folder), not a hardened container.
- The network guard covers this application. Ollama is a separate program; the Audit Logs page
  shows its connections too, and running with Wi-Fi off is the complete proof.
- The sample SOPs and inspection report are synthetic and written for this demo.
