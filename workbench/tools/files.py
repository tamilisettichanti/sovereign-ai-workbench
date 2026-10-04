"""File access for the agent, restricted to the project's own folders."""
from pathlib import Path

from ..config import KB_DIR, OUTPUTS, SAMPLES_DIR, UPLOADS

READ_ROOTS = [UPLOADS, OUTPUTS, SAMPLES_DIR, KB_DIR]


def safe_name(filename, default_ext):
    """Strip any path and unsafe characters; force the wanted extension."""
    name = Path(str(filename or "output")).name
    name = "".join(c if c.isalnum() or c in "-_. " else "_" for c in name).strip(" .") or "output"
    if not name.lower().endswith(default_ext):
        name = Path(name).stem + default_ext
    return name


def resolve_input(path):
    """Find a file by name inside the allowed folders. Anything outside them is refused."""
    name = Path(str(path).strip().strip('"\'')).name
    for root in READ_ROOTS:
        candidate = root / name
        if candidate.is_file():
            return candidate
    # tolerate small naming slips from the model (case, missing extension)
    for root in READ_ROOTS:
        for f in root.iterdir():
            if f.is_file() and (f.name.lower() == name.lower() or f.stem.lower() == Path(name).stem.lower()):
                return f
    raise FileNotFoundError(f"'{name}' was not found. Available files: {', '.join(available()) or 'none'}")


def available():
    names = []
    for root in (UPLOADS, SAMPLES_DIR, OUTPUTS):
        names += sorted(f.name for f in root.iterdir() if f.is_file())
    return names


def list_files(args, ctx):
    lines = []
    for label, root in (("Uploaded", UPLOADS), ("Samples", SAMPLES_DIR), ("Generated", OUTPUTS)):
        files = sorted(f.name for f in root.iterdir() if f.is_file())
        lines.append(f"{label}: {', '.join(files) if files else '(none)'}")
    return {"ok": True, "output": "\n".join(lines)}
