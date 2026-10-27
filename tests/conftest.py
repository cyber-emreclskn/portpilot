"""Shared fixtures: real listening processes we can safely inspect and kill."""

from __future__ import annotations

import socket
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest

SERVER = """
import socket, sys, time
s = socket.socket()
s.bind(("127.0.0.1", 0))
s.listen()
print(s.getsockname()[1], flush=True)
time.sleep(120)
"""


@dataclass
class Listener:
    proc: subprocess.Popen[str]
    port: int

    @property
    def pid(self) -> int:
        return self.proc.pid

    def is_alive(self) -> bool:
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            return True
        return False


@pytest.fixture
def spawn_listener() -> Iterator[Callable[[], Listener]]:
    """Factory that starts throwaway processes listening on a random port."""
    started: list[Listener] = []

    def _spawn() -> Listener:
        proc = subprocess.Popen([sys.executable, "-c", SERVER], stdout=subprocess.PIPE, text=True)
        assert proc.stdout is not None
        port = int(proc.stdout.readline())
        listener = Listener(proc, port)
        started.append(listener)
        return listener

    yield _spawn

    for listener in started:
        if listener.proc.poll() is None:
            listener.proc.kill()
            listener.proc.wait(timeout=5)


@pytest.fixture
def listener(spawn_listener: Callable[[], Listener]) -> Listener:
    return spawn_listener()


@pytest.fixture
def free_port() -> int:
    """A port with (almost certainly) nothing listening on it."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
    return port
