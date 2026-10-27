"""Render docs/screenshot.svg from representative sample data.

Run from the repository root:  uv run python docs/render_screenshot.py
"""

import asyncio

from portpilot import app as app_mod
from portpilot.core import PortInfo


def row(port, ip, pid, name, cmd, mem, t):
    return PortInfo(
        port=port, ip=ip, pid=pid, name=name, cmdline=cmd, user="emre", created=t, memory=mem
    )


SAMPLE = [
    row(3000, "::", 48211, "node", "node .next/standalone/server.js", "212.4MB", "09:14:02"),
    row(5000, "127.0.0.1", 48390, "python3", "python3 -m flask run", "61.8MB", "09:20:47"),
    row(
        5432,
        "127.0.0.1",
        1187,
        "postgres",
        "postgres -D /usr/local/var/postgres",
        "28.3MB",
        "08:01:13",
    ),
    row(
        6379, "127.0.0.1", 1204, "redis-server", "redis-server 127.0.0.1:6379", "9.6MB", "08:01:15"
    ),
    row(8000, "0.0.0.0", 48877, "python3", "python3 manage.py runserver", "94.1MB", "10:02:39"),
    row(8080, "0.0.0.0", 49012, "uvicorn", "uvicorn api.main:app --reload", "88.7MB", "10:05:11"),
    row(11434, "127.0.0.1", 932, "ollama", "ollama serve", "512.0MB", "08:00:58"),
    row(
        27017,
        "127.0.0.1",
        1251,
        "mongod",
        "mongod --config /usr/local/etc/mongod.conf",
        "143.2MB",
        "08:01:20",
    ),
]
app_mod.get_listening_ports = lambda: SAMPLE


async def main():
    a = app_mod.PortPilotApp()
    async with a.run_test(size=(124, 24)) as pilot:
        await pilot.pause(0.3)
        a.query_one("#port-table").move_cursor(row=4)
        await pilot.pause(0.3)
        a.save_screenshot("docs/screenshot.svg")


asyncio.run(main())
