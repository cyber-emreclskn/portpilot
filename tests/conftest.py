"""Shared fixtures: real listening processes we can safely inspect and kill."""

from __future__ import annotations

import contextlib
import socket
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import psutil
import pytest

# The server reports its own PID: on Windows, a venv's python.exe is a launcher
# that runs the real interpreter as a child process, so Popen.pid would be the
# launcher rather than the process that owns the socket.
SERVER = """
import os, socket, time
s = socket.socket()
s.bind(("127.0.0.1", 0))
s.listen()
print(s.getsockname()[1], os.getpid(), flush=True)
time.sleep(120)
"""


@dataclass
class Listener:
    proc: subprocess.Popen[str]
    port: int
    pid: int  # PID of the process that owns the listening socket

    def is_alive(self) -> bool:
        """Wait briefly for the server to exit; True if it is still running."""
        try:
            psutil.Process(self.pid).wait(timeout=3)
        except psutil.NoSuchProcess:
            return False
        except psutil.TimeoutExpired:
            return True
        return False


@pytest.fixture
def spawn_listener() -> Iterator[Callable[[], Listener]]:
    """Factory that starts throwaway processes listening on a random port."""
    started: list[Listener] = []

    def _spawn() -> Listener:
        proc = subprocess.Popen([sys.executable, "-c", SERVER], stdout=subprocess.PIPE, text=True)
        assert proc.stdout is not None
        port, pid = map(int, proc.stdout.readline().split())
        listener = Listener(proc, port, pid)
        started.append(listener)
        return listener

    yield _spawn

    for listener in started:
        with contextlib.suppress(psutil.NoSuchProcess):
            psutil.Process(listener.pid).kill()
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
