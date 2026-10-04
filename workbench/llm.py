"""Client for the local Ollama server. Every call is written to the audit log."""
import json
import threading
import time

import requests

from . import audit
from .config import EMBED_MODEL, KEEP_ALIVE, NUM_CTX, OLLAMA_URL

_session = requests.Session()
_session.trust_env = False  # ignore any system proxy: we only ever talk to 127.0.0.1

_tags_cache = {"at": 0.0, "data": {}}


class LLMError(RuntimeError):
    pass


# One AI task at a time. This laptop can hold one large model in memory, so two tasks
# running together would keep unloading each other's model. A second task waits here.
_task_lock = threading.Lock()


def is_busy():
    return _task_lock.locked()


def acquire_task():
    _task_lock.acquire()


def release_task():
    if _task_lock.locked():
        _task_lock.release()


def _post(path, payload, stream=False, timeout=900):
    try:
        r = _session.post(OLLAMA_URL + path, json=payload, stream=stream, timeout=timeout)
    except requests.RequestException as e:
        raise LLMError(f"Cannot reach the local Ollama server at {OLLAMA_URL}. "
                       f"Start Ollama and try again. ({type(e).__name__})") from e
    if r.status_code != 200:
        try:
            detail = r.json().get("error", r.text)
        except ValueError:
            detail = r.text
        raise LLMError(f"Ollama error: {detail}")
    return r


def make_room_for(model):
    """Unload every other chat model before using this one.

    On a 16 GB machine two 7B models do not fit in RAM together; holding both makes
    Windows swap to disk and generation slows to a crawl. The small embedding model stays.
    """
    try:
        loaded = _session.get(OLLAMA_URL + "/api/ps", timeout=5).json().get("models", [])
    except (requests.RequestException, ValueError):
        return
    for m in loaded:
        name = m.get("name", "")
        if name != model and not name.startswith(EMBED_MODEL):
            try:
                _session.post(OLLAMA_URL + "/api/generate", json={"model": name, "keep_alive": 0}, timeout=30)
            except requests.RequestException:
                pass


def _audit(model, path, purpose, user, started, final, error=None):
    audit.log(
        "model_call", user=user, model=model, endpoint=OLLAMA_URL + path, purpose=purpose,
        prompt_tokens=(final or {}).get("prompt_eval_count"),
        output_tokens=(final or {}).get("eval_count"),
        duration_ms=int((time.time() - started) * 1000),
        error=error,
    )


def chat_stream(model, messages, *, tools=None, user="system", purpose="chat",
                num_ctx=NUM_CTX, temperature=0.2, num_predict=None):
    """Yields {"token": str} while generating, then one {"done": True, "message": {...}}."""
    options = {"num_ctx": num_ctx, "temperature": temperature}
    if num_predict:
        options["num_predict"] = num_predict
    payload = {"model": model, "messages": messages, "stream": True,
               "options": options, "keep_alive": KEEP_ALIVE}
    if tools:
        payload["tools"] = tools
    make_room_for(model)
    started = time.time()
    content, tool_calls, final = [], [], None
    try:
        r = _post("/api/chat", payload, stream=True)
        for line in r.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            if chunk.get("error"):
                raise LLMError(f"Ollama error: {chunk['error']}")
            msg = chunk.get("message") or {}
            if msg.get("tool_calls"):
                tool_calls.extend(msg["tool_calls"])
            piece = msg.get("content") or ""
            if piece:
                content.append(piece)
                yield {"token": piece}
            if chunk.get("done"):
                final = chunk
    except LLMError as e:
        _audit(model, "/api/chat", purpose, user, started, None, error=str(e))
        raise
    _audit(model, "/api/chat", purpose, user, started, final)
    message = {"role": "assistant", "content": "".join(content)}
    if tool_calls:
        message["tool_calls"] = tool_calls
    yield {"done": True, "message": message,
           "duration_s": round(time.time() - started, 1),
           "output_tokens": (final or {}).get("eval_count")}


def chat(model, messages, **kwargs):
    """Non-streaming convenience wrapper. Returns the assistant message dict."""
    result = None
    for ev in chat_stream(model, messages, **kwargs):
        if ev.get("done"):
            result = ev["message"]
    return result


def embed(texts, user="system"):
    started = time.time()
    try:
        r = _post("/api/embed", {"model": EMBED_MODEL, "input": texts, "keep_alive": KEEP_ALIVE},
                  timeout=300)
    except LLMError as e:
        _audit(EMBED_MODEL, "/api/embed", "embed", user, started, None, error=str(e))
        raise
    data = r.json()
    _audit(EMBED_MODEL, "/api/embed", "embed", user, started, data)
    return data["embeddings"]


def installed(force=False):
    """{model name with tag: size in bytes} for models present in the local Ollama store."""
    if not force and time.time() - _tags_cache["at"] < 5:
        return _tags_cache["data"]
    try:
        r = _session.get(OLLAMA_URL + "/api/tags", timeout=5)
        data = {m["name"]: m.get("size", 0) for m in r.json().get("models", [])}
    except (requests.RequestException, ValueError):
        data = {}
    _tags_cache.update(at=time.time(), data=data)
    return data


def is_up():
    try:
        return _session.get(OLLAMA_URL + "/api/version", timeout=3).status_code == 200
    except requests.RequestException:
        return False


def version():
    try:
        return _session.get(OLLAMA_URL + "/api/version", timeout=3).json().get("version", "")
    except (requests.RequestException, ValueError):
        return ""
