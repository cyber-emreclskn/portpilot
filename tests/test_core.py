from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import psutil
import pytest

from portpilot import core
from portpilot.core import PortInfo, filter_connections, killable_pids

from .conftest import Listener


def make(port: int, pid: int | str = 1, name: str = "proc", cmd: str = "proc") -> PortInfo:
    return PortInfo(
        port=port,
        ip="127.0.0.1",
        pid=pid,
        name=name,
        cmdline=cmd,
        user="me",
        created="-",
        memory="-",
    )


SAMPLE = [
    make(3000, 101, "node", "node server.js"),
    make(5432, 202, "postgres", "postgres -D /data"),
    make(8000, 303, "python", "python manage.py runserver"),
    make(8000, 303, "python", "python manage.py runserver"),  # IPv6 twin
    make(9999, "-", "-", "-"),
]


# ------------------------------------------------------------------ filtering


@pytest.mark.parametrize(
    ("text", "expected_ports"),
    [
        ("", [3000, 5432, 8000, 8000, 9999]),
        ("node", [3000]),
        ("NODE", [3000]),  # case-insensitive
        ("543", [5432]),  # partial port
        ("303", [8000, 8000]),  # pid
        ("manage.py", [8000, 8000]),  # command line
        ("nothing-matches", []),
    ],
)
def test_filter_free_text(text: str, expected_ports: list[int]) -> None:
    assert [c["port"] for c in filter_connections(SAMPLE, text)] == expected_ports


def test_filter_by_exact_port_does_not_match_substrings() -> None:
    assert filter_connections(SAMPLE, port=543) == []
    assert [c["pid"] for c in filter_connections(SAMPLE, port=5432)] == [202]


def test_filter_by_name() -> None:
    assert [c["port"] for c in filter_connections(SAMPLE, name="post")] == [5432]


def test_killable_pids_dedupes_and_skips_unknown() -> None:
    assert killable_pids(SAMPLE) == [101, 202, 303]


# ------------------------------------------------------------------ discovery


def test_finds_real_listener(listener: Listener) -> None:
    matches = filter_connections(core.get_listening_ports(), port=listener.port)
    assert len(matches) == 1
    info = matches[0]
    assert info["pid"] == listener.pid
    assert info["ip"] == "127.0.0.1"
    assert "python" in info["name"].lower()
    assert info["memory"].endswith("MB")


def test_results_are_sorted_and_unique(spawn_listener: Callable[[], Listener]) -> None:
    spawn_listener()
    spawn_listener()
    ports = core.get_listening_ports()
    keys = [(c["port"], c["ip"], c["pid"]) for c in ports]
    assert keys == sorted(keys, key=lambda k: (k[0], k[1]))
    assert len(keys) == len(set(keys))


def test_falls_back_when_net_connections_denied(
    monkeypatch: pytest.MonkeyPatch, listener: Listener
) -> None:
    """macOS raises AccessDenied for system-wide lookups without root."""

    def denied(*_: Any, **__: Any) -> None:
        raise psutil.AccessDenied()

    monkeypatch.setattr(psutil, "net_connections", denied)
    matches = filter_connections(core.get_listening_ports(), port=listener.port)
    assert [m["pid"] for m in matches] == [listener.pid]


def test_uninspectable_process_still_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = SimpleNamespace(laddr=SimpleNamespace(ip="0.0.0.0", port=80), status="LISTEN", pid=1)
    monkeypatch.setattr(psutil, "net_connections", lambda kind: [conn])

    def denied(pid: int) -> None:
        raise psutil.AccessDenied(pid)

    monkeypatch.setattr(psutil, "Process", denied)
    [info] = core.get_listening_ports()
    assert info["port"] == 80
    assert info["pid"] == 1
    assert info["name"] == "-"


def test_socket_without_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = SimpleNamespace(laddr=SimpleNamespace(ip="::", port=22), status="LISTEN", pid=None)
    monkeypatch.setattr(psutil, "net_connections", lambda kind: [conn])
    [info] = core.get_listening_ports()
    assert info["pid"] == "-"
    assert killable_pids([info]) == []


# ------------------------------------------------------------------ killing


def test_kill_terminates_process(listener: Listener) -> None:
    ok, message = core.kill_process(listener.pid)
    assert ok, message
    assert not listener.is_alive()


def test_force_kill(listener: Listener) -> None:
    ok, _ = core.kill_process(listener.pid, force=True)
    assert ok
    assert not listener.is_alive()


def test_kill_missing_pid(listener: Listener) -> None:
    server = psutil.Process(listener.pid)
    server.kill()
    server.wait(timeout=5)
    ok, message = core.kill_process(listener.pid)
    assert not ok
    assert "not found" in message


@pytest.mark.parametrize(
    ("error", "fragment"),
    [
        (psutil.AccessDenied(1), "Access denied"),
        (psutil.TimeoutExpired(3, 1), "didn't terminate"),
    ],
)
def test_kill_error_messages(
    monkeypatch: pytest.MonkeyPatch, error: Exception, fragment: str
) -> None:
    class FakeProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def name(self) -> str:
            return "fake"

        def terminate(self) -> None:
            if isinstance(error, psutil.AccessDenied):
                raise error

        def wait(self, timeout: float) -> None:
            raise error

    monkeypatch.setattr(psutil, "Process", FakeProcess)
    ok, message = core.kill_process(1)
    assert not ok
    assert fragment in message
