"""Runs the demo scenarios without the web UI and prints PASS / FAIL for each.

    python scripts/smoke_test.py            all scenarios
    python scripts/smoke_test.py code       one scenario: routing | agent | code | vision | audit
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from workbench import agent, audit, netguard, registry, router  # noqa: E402
from workbench.config import OLLAMA_URL, OUTPUTS  # noqa: E402
from workbench.tools import sandbox  # noqa: E402
from workbench.tools.ocr import extract_text  # noqa: E402

RESULTS = []


def check(name, ok, note=""):
    RESULTS.append((name, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {note}" if note else ""))


def run(message, attachments=()):
    """Run a task, echo its events, return (answer text, files, events)."""
    answer, files, events = [], [], []
    for ev in agent.run_task(message, attachments, user="smoke-test"):
        events.append(ev)
        t = ev["type"]
        if t == "route":
            print(f"  route -> {ev['task']} / {ev['model']} ({ev['reason']})")
        elif t == "plan":
            for i, s in enumerate(ev["steps"], 1):
                print(f"  plan {i}. {s}")
        elif t == "step" and ev["status"] != "running":
            print(f"  step {ev['id']} [{ev['status']}] {ev['title']}")
        elif t == "token":
            answer.append(ev["text"])
        elif t == "answer_reset":
            answer = []
        elif t == "file":
            files.append(ev["name"])
            print(f"  file -> {ev['name']}")
        elif t == "error":
            print(f"  ERROR {ev['message']}")
        elif t == "done":
            print(f"  done in {ev['duration_s']} s")
    return "".join(answer), files, events


def test_routing():
    print("\n1. Model auto-selection")
    cases = [("Summarise this document and highlight the key points", ["manual.pdf"]),
             ("Write a Python function that converts bar to psi", []),
             ("Explain what this diagram shows", ["pid_crude_preheat.png"])]
    chosen = []
    for msg, att in cases:
        d = router.route(msg, att, log=False)
        chosen.append(d["model"])
        print(f"  {d['task']:7} -> {d['model']}   ({msg})")
    check("three task types go to three different models", None not in chosen and len(set(chosen)) == 3)


def test_agent():
    print("\n2. Agentic task: scanned inspection report -> approval note (Word)")
    answer, files, _ = run(
        "Read the scanned inspection report, pull out the key findings, check them against our "
        "SOP limits, and draft an approval note as a Word file.",
        ["inspection_report_E204.png"])
    docx_files = [f for f in files if f.endswith(".docx")]
    check("a Word file was created", bool(docx_files))
    if docx_files:
        text = extract_text(OUTPUTS / docx_files[-1])["text"]
        check("the note contains findings from the scan", "E-204" in text and ("9.2" in text or "gasket" in text.lower()),
              f"{len(text)} characters")
    print("  answer:", answer.strip()[:300])


def test_code():
    print("\n3. Coding task verified in the sandbox")
    answer, files, events = run(
        "Write a Python function remaining_life(nominal, measured, minimum, years_in_service) for a "
        "vessel wall. Corrosion rate = (nominal - measured) / years_in_service. Remaining life = "
        "(measured - minimum) / corrosion rate. Return both. Test it with nominal 12.0, measured 9.2, "
        "minimum 8.5 and 10 years: assert the corrosion rate is 0.28 mm/year and the remaining life is "
        "2.5 years (use round to 2 decimals), then print both.")
    passed = any(e["type"] == "step" and e.get("tool") == "run_python" and e["status"] == "done" for e in events)
    check("code ran successfully in the sandbox", passed)
    check("the verified output has the right numbers", "0.28" in answer and "2.5" in answer and "-2.5" not in answer)
    r = sandbox.run("import urllib.request\nurllib.request.urlopen('http://example.com')")
    check("the sandbox blocks network access", not r["ok"] and "disabled in the sandbox" in r["stderr"])


def test_vision():
    print("\n4. Multimodal task: P&ID drawing")
    if registry.pick("vision") is None:
        check("a vision model is installed", False, "llava is not downloaded yet")
        return
    answer, _, _ = run("Explain what this diagram shows and list the equipment tags.", ["pid_crude_preheat.png"])
    found = [t for t in ("T-101", "P-101", "E-204", "C-101", "FCV-101") if t in answer]
    check("equipment tags from the drawing are in the answer", len(found) >= 3, f"found {found}")
    print("  answer:", answer.strip()[:400])


def test_audit():
    print("\n5. Sovereignty: no external calls")
    calls = audit.read(limit=100000, kind=("model_call",))
    endpoints = {c["endpoint"].split("/api")[0] for c in calls}
    check("every model call went to the local Ollama server", endpoints <= {OLLAMA_URL}, f"{len(calls)} calls, endpoints {endpoints}")
    try:
        import requests
        requests.get("http://example.com", timeout=5)
        check("outbound connections are refused", False)
    except Exception:
        check("outbound connections are refused", True, "attempt was blocked and logged")
    snap = netguard.snapshot()
    own = [c for c in snap["connections"] if c["external"] and "ollama" not in c["process"].lower()]
    check("this app holds no external connections", not own, f"{len(snap['connections'])} live connections inspected")


if __name__ == "__main__":
    netguard.install()
    tests = {"routing": test_routing, "agent": test_agent, "code": test_code,
             "vision": test_vision, "audit": test_audit}
    wanted = sys.argv[1:] or list(tests)
    started = time.time()
    for name in wanted:
        tests[name]()
    print(f"\n{sum(ok for _, ok in RESULTS)}/{len(RESULTS)} checks passed in {round(time.time() - started)} s")
    sys.exit(0 if all(ok for _, ok in RESULTS) else 1)
