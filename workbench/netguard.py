"""Proof of the sovereign claim.

install()  - refuses any outbound connection from this process that is not loopback,
             and records the attempt.
snapshot() - lists the live network connections of this app and of Ollama, so the UI
             can show that none of them leave the machine.
"""
import ipaddress
import socket
import threading
from datetime import datetime

import psutil

from . import audit

_installed = False
_blocked = []
_lock = threading.Lock()
_HOSTNAME = socket.gethostname().lower()

_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex
_orig_getaddrinfo = socket.getaddrinfo


def is_loopback(host):
    if host in (None, "", b""):
        return True
    if isinstance(host, bytes):
        host = host.decode(errors="ignore")
    host = str(host).strip("[]").lower().split("%")[0]
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_unspecified


def _record(dest, via):
    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "dest": str(dest), "via": via}
    with _lock:
        _blocked.append(entry)
        del _blocked[:-200]
    audit.log("network_blocked", dest=str(dest), via=via)


def _check_address(sock, address, via):
    if sock.family in (socket.AF_INET, socket.AF_INET6) and isinstance(address, tuple):
        if not is_loopback(address[0]):
            _record(f"{address[0]}:{address[1]}", via)
            raise PermissionError(
                f"Sovereign mode: outbound connection to {address[0]}:{address[1]} blocked")


def _guarded_connect(self, address):
    _check_address(self, address, "connect")
    return _orig_connect(self, address)


def _guarded_connect_ex(self, address):
    _check_address(self, address, "connect")
    return _orig_connect_ex(self, address)


def _guarded_getaddrinfo(host, *args, **kwargs):
    h = host.decode(errors="ignore") if isinstance(host, bytes) else host
    if not (is_loopback(h) or (isinstance(h, str) and h.lower() == _HOSTNAME)):
        _record(h, "dns")
        raise socket.gaierror(f"Sovereign mode: name lookup for {h} blocked")
    return _orig_getaddrinfo(host, *args, **kwargs)


def install():
    global _installed
    if _installed:
        return
    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex
    socket.getaddrinfo = _guarded_getaddrinfo
    _installed = True
    audit.log("netguard_installed", note="non-loopback connections are refused")


def blocked():
    with _lock:
        return list(reversed(_blocked))


def _watched_processes():
    procs = {}
    try:
        me = psutil.Process()
        procs[me.pid] = me
        for child in me.children(recursive=True):
            procs[child.pid] = child
    except psutil.Error:
        pass
    for p in psutil.process_iter(["name"]):
        try:
            if "ollama" in (p.info["name"] or "").lower():
                procs[p.pid] = p
        except psutil.Error:
            continue
    return procs.values()


def snapshot():
    rows = []
    for p in _watched_processes():
        try:
            name = p.name()
            getter = getattr(p, "net_connections", None) or p.connections
            conns = getter(kind="inet")
        except psutil.Error:
            continue
        for c in conns:
            remote = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else ""
            external = bool(c.raddr) and not is_loopback(c.raddr.ip)
            rows.append({
                "pid": p.pid,
                "process": name,
                "local": f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "",
                "remote": remote,
                "status": c.status if c.status != "NONE" else "",
                "external": external,
            })
    rows.sort(key=lambda r: (not r["external"], r["process"], r["local"]))
    return {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "guard_installed": _installed,
        "connections": rows,
        "external_count": sum(1 for r in rows if r["external"]),
        "blocked": blocked()[:50],
    }
