"""Model router: looks at the task and picks the local model best suited to it."""
import re
from pathlib import Path

from . import audit, registry
from .config import IMAGE_EXTS

TASK_CAPABILITY = {"vision": "vision", "code": "code", "agent": "tools", "chat": "fast"}

TASK_LABEL = {
    "vision": "Visual understanding",
    "code": "Coding",
    "agent": "Document / multi-step agent task",
    "chat": "General question",
}

_CODE = re.compile(
    r"```|\b(code|python|script|function|program|algorithm|debug|bug|sql|regex|"
    r"unit test|javascript|java|compile|refactor)\b", re.I)
_DELIVERABLE = re.compile(
    r"\b(approval note|draft|word|docx|excel|xlsx|spreadsheet|ppt|pptx|powerpoint|"
    r"presentation|slides|report|memo)\b", re.I)
_SUMMARY = re.compile(r"\bsummar\w+\b", re.I)
_KNOWLEDGE = re.compile(
    r"\b(sops?|manuals?|procedures?|knowledge base|policy|standards?|according to|as per|"
    r"inspection|maintenance)\b", re.I)
_CALC = re.compile(r"\b(calculate|calculation|compute)\b", re.I)


def classify(message, attachments=()):
    """Returns (task_type, reason)."""
    exts = [Path(a).suffix.lower() for a in attachments]
    has_image = any(e in IMAGE_EXTS for e in exts)
    has_doc = any(e not in IMAGE_EXTS for e in exts)
    wants_file = bool(_DELIVERABLE.search(message))

    if has_image and not has_doc and not wants_file:
        return "vision", "an image is attached and the request is to understand it"
    if _CODE.search(message) and not attachments and not wants_file:
        return "code", "the request is about writing or fixing code"
    if attachments:
        return "agent", "a document is attached, so it must be read with tools"
    if wants_file or _SUMMARY.search(message):
        return "agent", "the request asks for a deliverable or summary, which needs tools"
    if _KNOWLEDGE.search(message):
        return "agent", "the request refers to internal procedures, so the knowledge base is needed"
    if _CALC.search(message):
        return "agent", "the request needs a calculation, which is run in the sandbox"
    return "chat", "a short general question with no files or tools needed"


def route(message, attachments=(), user="system", log=True, force=None):
    """`force` skips classification, for pages that are dedicated to one task type."""
    if force:
        task, reason = force, "requested from a page dedicated to this task type"
    else:
        task, reason = classify(message, attachments)
    wanted = TASK_CAPABILITY[task]
    model = registry.pick(wanted)
    fallback = None
    if model is None:
        for cap in registry.fallbacks().get(wanted, []):
            model = registry.pick(cap)
            if model:
                fallback = f"no usable '{wanted}' model, fell back to '{cap}'"
                break
    decision = {
        "task": task,
        "task_label": TASK_LABEL[task],
        "capability": wanted,
        "model": model["name"] if model else None,
        "model_label": model["label"] if model else None,
        "reason": reason,
        "fallback": fallback,
    }
    if log:
        audit.log("route", user=user, request=message[:120], **decision)
    return decision
