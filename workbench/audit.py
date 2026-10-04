"""Append-only audit log: one JSON object per line in logs/audit.jsonl."""
import json
import threading
from datetime import datetime

from .config import LOGS_DIR

AUDIT_FILE = LOGS_DIR / "audit.jsonl"
_lock = threading.Lock()


def log(kind, user="system", **fields):
    record = {"ts": datetime.now().isoformat(timespec="seconds"), "kind": kind, "user": user}
    record.update(fields)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with _lock:
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    return record


def read(limit=200, kind=None):
    """Newest first."""
    if not AUDIT_FILE.exists():
        return []
    with _lock:
        lines = AUDIT_FILE.read_text(encoding="utf-8").splitlines()
    out = []
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if kind and rec.get("kind") not in kind:
            continue
        out.append(rec)
        if len(out) >= limit:
            break
    return out


def count(kind):
    return sum(1 for r in read(limit=100000, kind=(kind,)))
