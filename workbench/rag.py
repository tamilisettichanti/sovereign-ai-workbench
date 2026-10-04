"""Local knowledge base (RAG).

ingest:   file -> text (OCR if scanned) -> overlapping chunks -> embeddings -> ChromaDB
retrieve: question -> embedding -> closest chunks, with a match percentage
answer:   the model answers using only the retrieved chunks and cites their sources

Embeddings come from nomic-embed-text in Ollama; ChromaDB is a folder on this disk.
"""
import shutil
from datetime import datetime
from pathlib import Path

from . import audit, llm, registry, rules
from .config import CHROMA_DIR, CHUNK_OVERLAP, CHUNK_SIZE, KB_DIR, TOP_K, WHOLE_DOC_LIMIT
from .tools.ocr import extract_text

_client = None


def _collection():
    global _client
    if _client is None:
        import logging

        import chromadb
        from chromadb.config import Settings
        # telemetry is switched off below; this silences its "failed to send" log lines
        logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR),
                                            settings=Settings(anonymized_telemetry=False))
    return _client.get_or_create_collection("knowledge_base", metadata={"hnsw:space": "cosine"})


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Pack whole lines into chunks of about `size` characters.

    Chunks never cut a line in half. Each new chunk repeats the last line or two of the
    previous one (the overlap) and starts with the document's title line for context.
    """
    lines = []
    for line in text.splitlines():
        line = line.strip()
        while len(line) > size:  # a single very long line: split on sentence ends
            cut = line.rfind(". ", 0, size) + 1 or size
            lines.append(line[:cut].strip())
            line = line[cut:].strip()
        if line:
            lines.append(line)
    if not lines:
        return []
    title = lines[0]
    chunks, current = [], []
    for line in lines:
        if current and sum(len(x) + 1 for x in current) + len(line) > size:
            chunks.append("\n".join(current))
            tail, used = [], 0
            for prev in reversed(current):
                if used + len(prev) > overlap:
                    break
                tail.insert(0, prev)
                used += len(prev)
            current = [f"[{title}]"] + tail
        current.append(line)
    if current:
        chunks.append("\n".join(current))
    return chunks


def _category(name):
    n = name.lower()
    if "sop" in n:
        return "SOPs"
    if "manual" in n:
        return "Technical Manuals"
    if "report" in n or "inspection" in n:
        return "Reports"
    if "safety" in n:
        return "Safety"
    return "General"


def ingest_file(path, user="system"):
    """Index one file. If it lives outside knowledge_base/ it is copied in first."""
    path = Path(path)
    if path.parent.resolve() != KB_DIR.resolve():
        target = KB_DIR / path.name
        shutil.copyfile(path, target)
        path = target
    text = extract_text(path)["text"]
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError(f"No readable text in {path.name}")
    col = _collection()
    col.delete(where={"source": path.name})
    vectors = []
    for i in range(0, len(chunks), 16):
        vectors += llm.embed(["search_document: " + c for c in chunks[i:i + 16]], user=user)
    added = datetime.now().isoformat(timespec="seconds")
    col.add(
        ids=[f"{path.name}::{i}" for i in range(len(chunks))],
        documents=chunks,
        embeddings=vectors,
        metadatas=[{"source": path.name, "chunk": i, "category": _category(path.name),
                    "added": added, "size_kb": round(path.stat().st_size / 1024, 1)}
                   for i in range(len(chunks))],
    )
    audit.log("kb_ingest", user=user, source=path.name, chunks=len(chunks))
    return {"source": path.name, "chunks": len(chunks)}


def ingest_folder(user="system"):
    results = []
    for f in sorted(KB_DIR.iterdir()):
        if f.is_file():
            results.append(ingest_file(f, user=user))
    return results


def list_documents():
    data = _collection().get(include=["metadatas"])
    docs = {}
    for meta in data["metadatas"]:
        d = docs.setdefault(meta["source"], {"source": meta["source"], "chunks": 0,
                                             "category": meta.get("category", "General"),
                                             "added": meta.get("added", ""),
                                             "size_kb": meta.get("size_kb", 0)})
        d["chunks"] += 1
    return sorted(docs.values(), key=lambda d: d["source"].lower())


def delete_document(source, user="system"):
    _collection().delete(where={"source": source})
    f = KB_DIR / Path(source).name
    if f.is_file():
        f.unlink()
    audit.log("kb_delete", user=user, source=source)


def stats():
    try:
        return {"documents": len(list_documents()), "chunks": _collection().count()}
    except Exception:
        return {"documents": 0, "chunks": 0}


def search(query, k=TOP_K, user="system"):
    col = _collection()
    if col.count() == 0:
        return []
    vector = llm.embed(["search_query: " + query], user=user)[0]
    res = col.query(query_embeddings=[vector], n_results=min(k, col.count()),
                    include=["documents", "metadatas", "distances"])
    hits = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append({"source": meta["source"], "chunk": meta["chunk"],
                     "category": meta.get("category", "General"), "text": doc,
                     "match": max(0, min(100, round((1 - dist) * 100)))})
    audit.log("kb_search", user=user, query=query[:120], hits=[h["source"] for h in hits])
    return hits


def _whole_best_document(hits):
    """Full text of the best-matching document if it is short, else None.

    A procedure read in fragments is easy to misapply: one passage holds a limit and the
    next holds its exception. Short documents are therefore given to the model whole.
    """
    path = KB_DIR / hits[0]["source"]
    if path.is_file():
        full = extract_text(path)["text"]
        if len(full) <= WHOLE_DOC_LIMIT:
            return full
    return None


def answer_stream(query, user="system"):
    """Yields {"sources": [...]}, then {"token": str}..., then {"done": True}."""
    hits = search(query, user=user)
    yield {"sources": hits}
    if not hits:
        yield {"token": "The knowledge base is empty. Add documents first."}
        yield {"done": True}
        return
    model = registry.pick("tools") or registry.pick("fast")
    if model is None:
        yield {"token": "No language model is available to write the answer."}
        yield {"done": True}
        return
    full = _whole_best_document(hits)
    if full:
        best = hits[0]["source"]
        others = [h for h in hits if h["source"] != best][:2]
        context = f"[Source: {best} | full document]\n{full}"
        context += "".join(f"\n\n[Source: {h['source']}]\n{h['text']}" for h in others)
    else:
        context = "\n\n".join(f"[Source: {h['source']}]\n{h['text']}" for h in hits)
    notes = rules.range_notes(context, rules.values_in(query))  # numeric limits are checked in code
    if notes:
        context += "\n\n" + notes
    messages = [
        {"role": "system", "content":
            "You answer questions for plant staff using ONLY the passages provided from the "
            "organisation's internal documents. If the passages do not contain the answer, say so. "
            "Be concise, use bullet points for procedures or limits, and name the source file "
            "for each point in brackets. When the answer depends on a numeric limit or range, quote "
            "the rule and state the comparison explicitly, for example '4.8 is not above 5, so the "
            "first range applies'."},
        {"role": "user", "content": f"Passages:\n{context}\n\nQuestion: {query}"},
    ]
    yield {"model": model["label"]}
    llm.acquire_task()  # waits here if another AI task is running
    try:
        for ev in llm.chat_stream(model["name"], messages, user=user, purpose="knowledge base answer"):
            if "token" in ev:
                yield {"token": ev["token"]}
    finally:
        llm.release_task()
    yield {"done": True}


def search_knowledge_base(args, ctx):
    query = str(args.get("query", "")).strip()
    if not query:
        return {"ok": False, "output": "Provide a search query."}
    hits = search(query, user=ctx.get("user", "system"))
    if not hits:
        return {"ok": True, "output": "No matching passages in the knowledge base.", "sources": []}
    # Within one task, do not hand back a document the agent already has: a second search
    # is usually after something else (the limits first, then the document format).
    given = ctx.setdefault("kb_given", set())
    fresh = [h for h in hits if h["source"] not in given]
    if not fresh:
        wider = search(query, k=TOP_K * 3, user=ctx.get("user", "system"))
        fresh = [h for h in wider if h["source"] not in given]
    if not fresh:
        return {"ok": True, "output": "Nothing new: the matching documents were already returned to you.",
                "sources": []}
    full = _whole_best_document(fresh)
    if full:
        best = fresh[0]["source"]
        given.add(best)
        return {"ok": True, "output": f"[Source: {best} | full document, match {fresh[0]['match']}%]\n{full}",
                "sources": [{"source": best, "match": fresh[0]["match"]}]}
    hits = fresh
    text = "\n\n".join(f"[Source: {h['source']} | match {h['match']}%]\n{h['text']}" for h in hits)
    return {"ok": True, "output": text, "sources": [{"source": h["source"], "match": h["match"]} for h in hits]}
