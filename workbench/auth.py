"""Local accounts only. Passwords are stored as salted PBKDF2 hashes in data/users.json.

On first start the accounts in config/demo_users.json are hashed into data/users.json.
"""
import hashlib
import hmac
import json
import secrets

from . import audit
from .config import CONFIG_DIR, DATA_DIR

SEED_FILE = CONFIG_DIR / "demo_users.json"
USERS_FILE = DATA_DIR / "users.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"   # so a server restart does not sign everyone out
_ITERATIONS = 200_000


def _load_sessions():
    try:
        return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_sessions():
    SESSIONS_FILE.write_text(json.dumps(_sessions), encoding="utf-8")


_sessions = _load_sessions()


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS).hex()


def ensure_users():
    if USERS_FILE.exists() or not SEED_FILE.exists():
        return
    users = {}
    for u in json.loads(SEED_FILE.read_text(encoding="utf-8")):
        salt = secrets.token_hex(16)
        users[u["username"].lower()] = {
            "username": u["username"], "name": u.get("name", u["username"]),
            "role": u.get("role", "User"), "salt": salt, "hash": _hash(u["password"], salt),
        }
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def _users():
    ensure_users()
    if not USERS_FILE.exists():
        return {}
    return json.loads(USERS_FILE.read_text(encoding="utf-8"))


def login(username, password):
    """Returns (token, public user dict) or (None, None)."""
    u = _users().get((username or "").strip().lower())
    if not u or not hmac.compare_digest(u["hash"], _hash(password or "", u["salt"])):
        audit.log("login_failed", user=(username or "")[:40])
        return None, None
    token = secrets.token_urlsafe(32)
    public = {"username": u["username"], "name": u["name"], "role": u["role"]}
    _sessions[token] = public
    _save_sessions()
    audit.log("login", user=u["username"])
    return token, public


def session(token):
    return _sessions.get(token) if token else None


def logout(token):
    u = _sessions.pop(token, None)
    if u:
        _save_sessions()
        audit.log("logout", user=u["username"])
