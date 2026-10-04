"""Paths, limits and offline switches. Everything the app touches lives under ROOT."""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

WEB_DIR = ROOT / "web"
KB_DIR = ROOT / "knowledge_base"
SAMPLES_DIR = ROOT / "samples"
WORKSPACE = ROOT / "workspace"
UPLOADS = WORKSPACE / "uploads"
OUTPUTS = WORKSPACE / "outputs"
SANDBOX_DIR = WORKSPACE / "sandbox"
LOGS_DIR = ROOT / "logs"
DATA_DIR = ROOT / "data"
CHROMA_DIR = DATA_DIR / "chroma"
CONFIG_DIR = ROOT / "config"

for _d in (KB_DIR, SAMPLES_DIR, UPLOADS, OUTPUTS, SANDBOX_DIR, LOGS_DIR, DATA_DIR, CONFIG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# The only network endpoint the backend is allowed to talk to.
OLLAMA_URL = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000

# Small-model, CPU-only limits.
NUM_CTX = 4096            # context window. One size for every call: changing it
AGENT_NUM_CTX = NUM_CTX   # between calls makes Ollama reload the model each time.
KEEP_ALIVE = "20m"        # keep a model in RAM between calls
MAX_AGENT_STEPS = 8
MAX_CODE_ATTEMPTS = 3
TOOL_OUTPUT_LIMIT = 3000  # characters of a tool result fed back to the model
WHOLE_DOC_LIMIT = 2800    # knowledge base documents up to this size go to the agent whole
SANDBOX_TIMEOUT = 20      # seconds
SANDBOX_OUTPUT_LIMIT = 4000

# RAG
CHUNK_SIZE = 600      # characters per chunk
CHUNK_OVERLAP = 150   # characters repeated from the previous chunk
TOP_K = 4

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
DOC_EXTS = {".pdf", ".docx", ".txt", ".md", ".csv", ".py", ".json", ".log"}

TESSERACT_CMD = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Libraries that like to phone home are told not to.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("DO_NOT_TRACK", "1")
