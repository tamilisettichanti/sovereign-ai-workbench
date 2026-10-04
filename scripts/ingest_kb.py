"""Index every file in knowledge_base/ into the local vector database."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from workbench import netguard, rag  # noqa: E402

if __name__ == "__main__":
    netguard.install()
    for r in rag.ingest_folder():
        print(f"indexed {r['source']}: {r['chunks']} chunks")
    print("knowledge base:", rag.stats())
