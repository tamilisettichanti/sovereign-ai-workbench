"""Loads models.yaml and merges it with what is actually installed in Ollama."""
import json
from pathlib import Path

import yaml

from . import llm
from .config import DATA_DIR

REGISTRY_FILE = Path(__file__).with_name("models.yaml")
STATE_FILE = DATA_DIR / "model_state.json"   # which models the admin has switched off


def _load_yaml():
    return yaml.safe_load(REGISTRY_FILE.read_text(encoding="utf-8"))


def _load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def _full_name(name):
    return name if ":" in name else name + ":latest"


def models():
    state = _load_state()
    have = llm.installed()
    out = []
    for m in _load_yaml().get("models", []):
        name = _full_name(m["name"])
        out.append({
            **m,
            "name": name,
            "installed": name in have,
            "size_gb": round(have.get(name, 0) / 1e9, 1),
            "enabled": state.get(name, True),
        })
    return out


def fallbacks():
    return _load_yaml().get("fallbacks", {})


def set_enabled(name, enabled):
    state = _load_state()
    state[_full_name(name)] = bool(enabled)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def pick(capability):
    """First usable model with the capability, or None."""
    for m in models():
        if capability in m["capabilities"] and m["enabled"] and m["installed"]:
            return m
    return None
