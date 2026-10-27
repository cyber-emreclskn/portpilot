"""PortPilot - Interactive Terminal UI for Port Management."""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from .core import (
    COMMON_PORTS,
    PortInfo,
    filter_connections,
    get_listening_ports,
    kill_process,
)

# Re-exported for backwards compatibility with code importing from portpilot.app
__all__ = ["ConfirmKillScreen", "PortPilotApp", "get_listening_ports", "kill_process", "main"]

COMMAND_WIDTH = 40


class ConfirmKillScreen(ModalScreen[bool]):
    """Modal screen for kill confirmation."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, port: int, pid: int, process_name: str) -> None:
        super().__init__()
        self.port = port
        self.pid = pid
        # Note: don't assign to ``self.name`` - it's a read-only property on Textual screens.
        self.process_name = process_name

    def compose(self) -> ComposeResult:
        with Container(id="confirm-dialog"):
            yield Static(f"⚠️  Kill process on port {self.port}?", id="confirm-title")
            yield Static(f"Process: {self.process_name}", classes="confirm-detail")
            yield Static(f"PID: {self.pid}", classes="confirm-detail")
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes [y]", variant="error", id="yes-btn")
                yield Button("No [n]", variant="primary", id="no-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes-btn":
            self.action_confirm()
        else:
            self.action_cancel()

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class PortPilotApp(App[None]):
    """Main PortPilot Application."""

    TITLE = "🛫 PortPilot"
    SUB_TITLE = "listening ports"

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        height: 100%;
    }

    #port-table {
        height: 1fr;
        margin: 1;
        border: solid $primary;
    }

    #status-bar {
        height: 3;
        padding: 1;
        background: $surface-darken-1;
    }

    #filter-container {
        height: 3;
        padding: 0 1;
    }

    #filter-input {
        width: 30;
    }

    #filter-label {
        padding: 1;
        width: auto;
    }

    #stats {
        dock: right;
        padding: 1;
        width: auto;
    }

    #confirm-dialog {
        width: 50;
        height: 12;
        padding: 1 2;
        background: $surface;
        border: thick $error;
    }

    #confirm-title {
        text-align: center;
        text-style: bold;
        padding: 1;
    }

    .confirm-detail {
        text-align: center;
        padding: 0 1;
    }

    #confirm-buttons {
        align: center middle;
        padding-top: 1;
        height: 3;
    }

    #confirm-buttons Button {
        margin: 0 1;
    }

    .status-success {
        color: $success;
    }

    .status-error {
        color: $error;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("k", "kill_selected", "Kill"),
        Binding("K", "force_kill", "Force Kill"),
        Binding("f", "focus_filter", "Filter"),
        Binding("/", "focus_filter", "Filter", show=False),
        Binding("escape", "clear_filter", "Clear Filter"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.connections: list[PortInfo] = []
        self.visible_rows: list[PortInfo] = []
        self.filter_text = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="main-container"):
            with Horizontal(id="filter-container"):
                yield Label("🔍 Filter:", id="filter-label")
                yield Input(placeholder="port, name, or pid...", id="filter-input")
                yield Static("", id="stats")
            yield DataTable(id="port-table")
            yield Static("Ready", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        # Keep direct references: while a modal is open, ``query_one`` searches the
        # modal screen on some Textual versions and wouldn't find these widgets.
        self.table: DataTable[Text | str] = self.query_one("#port-table", DataTable)
        self.filter_input = self.query_one("#filter-input", Input)
        self.stats = self.query_one("#stats", Static)
        self.status_bar = self.query_one("#status-bar", Static)
        table = self.table
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("Port", "IP", "PID", "Process", "Command", "User", "Started", "Memory")
        self.action_refresh()
        table.focus()

    def action_refresh(self) -> None:
        """Refresh the port list."""
        self.connections = get_listening_ports()
        self.update_table()
        self.update_status("Refreshed", "status-success")

    def update_table(self) -> None:
        """Rebuild the table from current connections and filter."""
        table = self.table
        table.clear()
        self.visible_rows = filter_connections(self.connections, self.filter_text)

        for conn in self.visible_rows:
            port_text = Text(str(conn["port"]))
            color = COMMON_PORTS.get(conn["port"])
            if color:
                port_text.stylize(color)
            cmd = conn["cmdline"]
            if len(cmd) > COMMAND_WIDTH:
                cmd = cmd[:COMMAND_WIDTH] + "..."
            table.add_row(
                port_text,
                conn["ip"],
                str(conn["pid"]),
                conn["name"],
                cmd,
                conn["user"],
                conn["created"],
                conn["memory"],
            )

        self.stats.update(f"📊 {len(self.visible_rows)}/{len(self.connections)} ports")

    def update_status(self, message: str, css_class: str = "") -> None:
        status = self.status_bar
        status.update(message)
        status.remove_class("status-success", "status-error")
        if css_class:
            status.add_class(css_class)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-input":
            self.filter_text = event.value
            self.update_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filter-input":
            self.table.focus()

    def action_focus_filter(self) -> None:
        self.filter_input.focus()

    def action_clear_filter(self) -> None:
        self.filter_input.value = ""
        self.filter_text = ""
        self.update_table()
        self.table.focus()

    def get_selected_connection(self) -> PortInfo | None:
        """Return the connection under the table cursor, if any."""
        row = self.table.cursor_row
        if row is not None and 0 <= row < len(self.visible_rows):
            return self.visible_rows[row]
        return None

    def _selected_target(self) -> PortInfo | None:
        conn = self.get_selected_connection()
        if conn is None or not isinstance(conn["pid"], int):
            self.update_status("No process selected or PID unavailable", "status-error")
            return None
        return conn

    def _kill(self, conn: PortInfo, *, force: bool) -> None:
        assert isinstance(conn["pid"], int)
        success, message = kill_process(conn["pid"], force=force)
        if success:
            verb = "🔥 Force killed" if force else "✅ Killed"
            self.update_status(f"{verb}: {conn['name']} on port {conn['port']}", "status-success")
            self.connections = get_listening_ports()
            self.update_table()
        else:
            self.update_status(f"❌ {message}", "status-error")

    def action_kill_selected(self) -> None:
        """Ask for confirmation, then terminate the selected process."""
        conn = self._selected_target()
        if conn is None:
            return
        assert isinstance(conn["pid"], int)

        # Capture the target now so a refresh while the dialog is open can't
        # change which process gets killed.
        def on_result(confirmed: bool | None) -> None:
            if confirmed:
                self._kill(conn, force=False)
            else:
                self.update_status("Kill cancelled")

        self.push_screen(ConfirmKillScreen(conn["port"], conn["pid"], conn["name"]), on_result)

    def action_force_kill(self) -> None:
        """Force kill the selected process (no confirmation)."""
        conn = self._selected_target()
        if conn is not None:
            self._kill(conn, force=True)


def main() -> None:
    """Entry point for the application."""
    PortPilotApp().run()


if __name__ == "__main__":
    main()
