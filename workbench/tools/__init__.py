"""Tool registry: the local tools the agent is allowed to call, with their schemas."""
import time

from .. import audit
from ..config import TOOL_OUTPUT_LIMIT
from . import files, ocr, office, sandbox, vision


def _kb_search(args, ctx):
    from .. import rag  # imported late: rag itself uses the OCR tool
    return rag.search_knowledge_base(args, ctx)


def _schema(name, description, properties, required):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required}}}


_S = {"type": "string"}

TOOLS = {
    "read_document": {
        "fn": ocr.read_document, "label": "OCR / Document reader",
        "schema": _schema(
            "read_document",
            "Read a file and return its text. Works for PDF, Word and text files, and for scanned "
            "pages or images of documents (on-device OCR is applied automatically).",
            {"path": {**_S, "description": "File name, e.g. inspection_report.png"}}, ["path"]),
    },
    "describe_image": {
        "fn": vision.describe_image, "label": "Vision model",
        "schema": _schema(
            "describe_image",
            "Look at a drawing, diagram or photograph with the local vision model and answer a "
            "question about it. Use for P&IDs, equipment photos and sketches.",
            {"path": {**_S, "description": "Image file name"},
             "question": {**_S, "description": "What to find out from the image"}}, ["path", "question"]),
    },
    "search_knowledge_base": {
        "fn": _kb_search, "label": "Knowledge base",
        "schema": _schema(
            "search_knowledge_base",
            "Search the organisation's internal SOPs, manuals and past reports. Returns the most "
            "relevant passages with their source file. Use it for limits, procedures and formats.",
            {"query": {**_S, "description": "What to look for"}}, ["query"]),
    },
    "run_python": {
        "fn": sandbox.run_python, "label": "Code sandbox",
        "schema": _schema(
            "run_python",
            "Run Python code in an isolated sandbox and return what it printed. Use it for "
            "calculations and data work. The code must print its results. No network access.",
            {"code": {**_S, "description": "Complete Python script"}}, ["code"]),
    },
    "create_word": {
        "fn": office.create_word, "label": "Word generator",
        "schema": _schema(
            "create_word",
            "Create a Word (.docx) document such as an approval note or report.",
            {"filename": {**_S, "description": "e.g. approval_note.docx"},
             "title": {**_S, "description": "Document title"},
             "content": {**_S, "description": "Full body text. Use '## Heading' lines for sections, "
                                              "'- ' for bullets and '| a | b |' rows for tables."}},
            ["filename", "title", "content"]),
    },
    "create_excel": {
        "fn": office.create_excel, "label": "Excel generator",
        "schema": _schema(
            "create_excel",
            "Create an Excel (.xlsx) spreadsheet.",
            {"filename": {**_S, "description": "e.g. findings.xlsx"},
             "content": {**_S, "description": "CSV text: first line is the header row, "
                                              "one row per line, values separated by commas."}},
            ["filename", "content"]),
    },
    "create_presentation": {
        "fn": office.create_presentation, "label": "PowerPoint generator",
        "schema": _schema(
            "create_presentation",
            "Create a PowerPoint (.pptx) presentation.",
            {"filename": {**_S, "description": "e.g. summary.pptx"},
             "title": {**_S, "description": "Presentation title"},
             "content": {**_S, "description": "Slides as text: '## Slide title' then '- bullet' lines."}},
            ["filename", "title", "content"]),
    },
    "list_files": {
        "fn": files.list_files, "label": "File system",
        "schema": _schema("list_files", "List the uploaded, sample and generated files.", {}, []),
    },
}


def schemas():
    return [t["schema"] for t in TOOLS.values()]


def label(name):
    return TOOLS.get(name, {}).get("label", name)


def execute(name, args, ctx):
    """Run one tool. Never raises: errors come back as a result the agent can react to."""
    started = time.time()
    tool = TOOLS.get(name)
    if tool is None:
        result = {"ok": False, "output": f"Unknown tool '{name}'. Available: {', '.join(TOOLS)}"}
    else:
        try:
            result = tool["fn"](args if isinstance(args, dict) else {}, ctx)
        except Exception as e:
            result = {"ok": False, "output": f"{type(e).__name__}: {e}"}
    output = result.get("output", "")
    if len(output) > TOOL_OUTPUT_LIMIT:
        result["output"] = output[:TOOL_OUTPUT_LIMIT] + "\n...[truncated]"
    result["duration_s"] = round(time.time() - started, 1)
    audit.log("tool_call", user=ctx.get("user", "system"), tool=name, ok=result["ok"],
              duration_ms=int((time.time() - started) * 1000),
              args={k: (str(v)[:80]) for k, v in (args or {}).items()} if isinstance(args, dict) else {},
              file=result.get("file"))
    return result
