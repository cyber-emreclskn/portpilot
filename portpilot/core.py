"""Core logic for PortPilot: discovering listening ports and killing processes.

This module has no UI dependencies so it can be unit-tested and reused by both
the CLI and the TUI.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, TypedDict

import psutil

#: Common development ports and the color used to highlight them.
COMMON_PORTS: dict[int, str] = {
    3000: "green",  # React / Next.js
    3001: "green",
    5000: "cyan",  # Flask
    5001: "cyan",
    8000: "yellow",  # Django / general
    8080: "yellow",
    5432: "magenta",  # PostgreSQL
    6379: "red",  # Redis
    27017: "green",  # MongoDB
}

MISSING = "-"


class PortInfo(TypedDict):
    port: int
    ip: str
    pid: int | str
    name: str
    cmdline: str
    user: str
    created: str
    memory: str


def _empty_info(port: int, ip: str, pid: int | None) -> PortInfo:
    return PortInfo(
        port=port,
        ip=ip,
        pid=pid if pid else MISSING,
        name=MISSING,
        cmdline=MISSING,
        user=MISSING,
        created=MISSING,
        memory=MISSING,
    )


def _describe(port: int, ip: str, pid: int | None) -> PortInfo:
    """Build a PortInfo record, tolerating processes we can't inspect."""
    info = _empty_info(port, ip, pid)
    if not pid:
        return info
    try:
        proc = psutil.Process(pid)
        with proc.oneshot():
            info["name"] = proc.name()
            info["cmdline"] = " ".join(proc.cmdline()[:3]) or MISSING
            info["user"] = proc.username()
            info["created"] = datetime.fromtimestamp(proc.create_time()).strftime("%H:%M:%S")
            info["memory"] = f"{proc.memory_info().rss / 1024 / 1024:.1f}MB"
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
    return info


def _system_listeners() -> list[tuple[int, str, int | None]]:
    """Return (port, ip, pid) for every listening inet socket.

    ``psutil.net_connections()`` needs root on macOS (and some other platforms)
    and raises ``AccessDenied`` otherwise. In that case we fall back to asking
    each process individually, which works for processes owned by the user.
    """
    try:
        conns: Iterable[Any] = psutil.net_connections(kind="inet")
        return [
            (c.laddr.port, c.laddr.ip, c.pid)
            for c in conns
            if c.status == psutil.CONN_LISTEN and c.laddr
        ]
    except psutil.AccessDenied:
        pass

    result: list[tuple[int, str, int | None]] = []
    for proc in psutil.process_iter():
        try:
            for c in proc.net_connections(kind="inet"):
                if c.status == psutil.CONN_LISTEN and c.laddr:
                    result.append((c.laddr.port, c.laddr.ip, proc.pid))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return result


def get_listening_ports() -> list[PortInfo]:
    """Get all listening ports with process information, sorted by port."""
    seen: set[tuple[int, str, int | None]] = set()
    connections: list[PortInfo] = []
    for port, ip, pid in _system_listeners():
        key = (port, ip, pid)
        if key in seen:
            continue
        seen.add(key)
        connections.append(_describe(port, ip, pid))
    return sorted(connections, key=lambda c: (c["port"], c["ip"]))


def filter_connections(
    connections: list[PortInfo],
    text: str = "",
    *,
    port: int | None = None,
    name: str | None = None,
) -> list[PortInfo]:
    """Filter connections by free text (port/name/pid/command), exact port, or name."""
    result = connections
    if port is not None:
        result = [c for c in result if c["port"] == port]
    if name:
        needle = name.lower()
        result = [c for c in result if needle in c["name"].lower()]
    if text:
        needle = text.lower()
        result = [
            c
            for c in result
            if needle in str(c["port"])
            or needle in c["name"].lower()
            or needle in str(c["pid"])
            or needle in c["cmdline"].lower()
        ]
    return result


def killable_pids(connections: list[PortInfo]) -> list[int]:
    """Unique, known PIDs in first-seen order."""
    pids: list[int] = []
    for c in connections:
        pid = c["pid"]
        if isinstance(pid, int) and pid not in pids:
            pids.append(pid)
    return pids


def kill_process(pid: int, force: bool = False, timeout: float = 3) -> tuple[bool, str]:
    """Terminate (or force kill) a process by PID. Returns (success, message)."""
    try:
        proc = psutil.Process(pid)
        proc_name = proc.name()
        if force:
            proc.kill()
        else:
            proc.terminate()
        proc.wait(timeout=timeout)
        return True, f"Process {proc_name} (PID: {pid}) terminated"
    except psutil.NoSuchProcess:
        return False, f"Process {pid} not found"
    except psutil.AccessDenied:
        return False, f"Access denied for PID {pid}. Try running with elevated privileges."
    except psutil.TimeoutExpired:
        return False, f"Process {pid} didn't terminate in time. Try force kill."
