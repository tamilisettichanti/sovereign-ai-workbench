"""Runs model-written Python in a restricted subprocess.

Isolation used: separate process, isolated interpreter mode (-I), its own empty working
folder, a hard timeout, capped output, and networking switched off inside the process.
This is process-level isolation, not a container.
"""
import ast
import os
import subprocess
import sys
import time
from datetime import datetime

from ..config import SANDBOX_DIR, SANDBOX_OUTPUT_LIMIT, SANDBOX_TIMEOUT

_RUNNER = '''import runpy, socket, sys

def _blocked(*args, **kwargs):
    raise PermissionError("Network access is disabled in the sandbox")

socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked
socket.gethostbyname = _blocked

sys.argv = ["main.py"]
runpy.run_path("main.py", run_name="__main__")
'''


def _clip(text):
    if len(text) > SANDBOX_OUTPUT_LIMIT:
        return text[:SANDBOX_OUTPUT_LIMIT] + "\n...[output truncated]"
    return text


def run(code, timeout=SANDBOX_TIMEOUT):
    workdir = SANDBOX_DIR / datetime.now().strftime("run_%Y%m%d_%H%M%S_%f")
    workdir.mkdir(parents=True)
    (workdir / "main.py").write_text(code, encoding="utf-8")
    (workdir / "_runner.py").write_text(_RUNNER, encoding="utf-8")

    env = {k: os.environ[k] for k in ("SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "PATH") if k in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    started = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "_runner.py"], cwd=workdir, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        result = {"exit_code": proc.returncode, "stdout": _clip(proc.stdout),
                  "stderr": _clip(proc.stderr), "timed_out": False}
    except subprocess.TimeoutExpired as e:
        result = {"exit_code": -1, "stdout": _clip(e.stdout or "") if isinstance(e.stdout, str) else "",
                  "stderr": f"Stopped: the code ran longer than {timeout} seconds.", "timed_out": True}
    result["ok"] = result["exit_code"] == 0
    result["duration_s"] = round(time.time() - started, 2)
    result["workdir"] = workdir.name
    return result


def format_result(r):
    parts = [f"exit code: {r['exit_code']} ({'success' if r['ok'] else 'failed'}) in {r['duration_s']}s"]
    if r["stdout"].strip():
        parts.append("stdout:\n" + r["stdout"].strip())
    if r["stderr"].strip():
        parts.append("stderr:\n" + r["stderr"].strip())
    return "\n".join(parts)


def _print_last_expression(code):
    """If the script ends with a bare expression (as in a notebook), print it.

    Models often finish with `result` instead of `print(result)`, which would show nothing.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code  # let the sandbox report the syntax error
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = tree.body[-1]
        is_call_to_print = (isinstance(last.value, ast.Call) and isinstance(last.value.func, ast.Name)
                            and last.value.func.id == "print")
        if not is_call_to_print:
            tree.body[-1] = ast.Expr(ast.Call(ast.Name("print", ast.Load()), [last.value], []))
            return ast.unparse(ast.fix_missing_locations(tree))
    return code


def run_python(args, ctx):
    code = args.get("code", "")
    if not isinstance(code, str) or not code.strip():
        return {"ok": False, "output": "No code was provided."}
    code = _print_last_expression(code)
    r = run(code)
    if r["ok"] and not r["stdout"].strip():
        r["stdout"] = "(the code ran but printed nothing: use print() to show results)"
    return {"ok": r["ok"], "output": format_result(r), "code": code}
