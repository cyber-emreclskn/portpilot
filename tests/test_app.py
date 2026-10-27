"""TUI tests driven headlessly through Textual's Pilot."""

from __future__ import annotations

from typing import Any

from textual.pilot import Pilot
from textual.widgets import DataTable, Input, Static

from portpilot.app import ConfirmKillScreen, PortPilotApp

from .conftest import Listener


async def _focus_on(app: PortPilotApp, pilot: Pilot[Any], port: int) -> None:
    app.query_one("#filter-input", Input).value = str(port)
    await pilot.pause()
    app.query_one("#port-table", DataTable).focus()
    await pilot.pause()


def _status(app: PortPilotApp) -> str:
    return str(app.query_one("#status-bar", Static).render())


async def test_starts_and_lists_ports(listener: Listener) -> None:
    app = PortPilotApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert any(c["port"] == listener.port for c in app.connections)
        assert app.query_one("#port-table", DataTable).row_count == len(app.visible_rows)


async def test_filter_narrows_rows(listener: Listener) -> None:
    app = PortPilotApp()
    async with app.run_test() as pilot:
        await _focus_on(app, pilot, listener.port)
        assert [c["pid"] for c in app.visible_rows] == [listener.pid]


async def test_escape_clears_filter(listener: Listener) -> None:
    app = PortPilotApp()
    async with app.run_test() as pilot:
        await _focus_on(app, pilot, listener.port)
        await pilot.press("escape")
        assert app.filter_text == ""
        assert len(app.visible_rows) == len(app.connections)


async def test_kill_opens_confirmation_and_kills(listener: Listener) -> None:
    """Regression: pressing `k` used to crash with
    "property 'name' of 'ConfirmKillScreen' object has no setter"."""
    app = PortPilotApp()
    async with app.run_test() as pilot:
        await _focus_on(app, pilot, listener.port)
        await pilot.press("k")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmKillScreen)
        assert app.screen.pid == listener.pid

        await pilot.press("y")
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmKillScreen)
        assert not listener.is_alive()
        assert "Killed" in _status(app)


async def test_kill_cancelled(listener: Listener) -> None:
    app = PortPilotApp()
    async with app.run_test() as pilot:
        await _focus_on(app, pilot, listener.port)
        await pilot.press("k")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert listener.is_alive()
        assert "cancelled" in _status(app)


async def test_kill_target_fixed_when_list_refreshes(listener: Listener) -> None:
    """The process shown in the dialog is the one killed, even after a refresh."""
    app = PortPilotApp()
    async with app.run_test() as pilot:
        await _focus_on(app, pilot, listener.port)
        await pilot.press("k")
        await pilot.pause()
        app.filter_text = ""
        app.action_refresh()  # cursor row now points elsewhere
        await pilot.press("y")
        await pilot.pause()
        assert not listener.is_alive()


async def test_force_kill(listener: Listener) -> None:
    app = PortPilotApp()
    async with app.run_test() as pilot:
        await _focus_on(app, pilot, listener.port)
        await pilot.press("K")
        await pilot.pause()
        assert not listener.is_alive()
        assert "Force killed" in _status(app)


async def test_kill_with_empty_selection(free_port: int) -> None:
    app = PortPilotApp()
    async with app.run_test() as pilot:
        await _focus_on(app, pilot, free_port)
        await pilot.press("k")
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmKillScreen)
        assert "No process selected" in _status(app)
