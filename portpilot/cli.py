"""Command-line interface for PortPilot."""

from __future__ import annotations

import json
import sys
import time
from typing import NoReturn

import click
import psutil
from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .core import PortInfo, filter_connections, get_listening_ports, kill_process, killable_pids

console = Console()
err_console = Console(stderr=True)

#: Exit codes (documented in the README)
EXIT_OK = 0
EXIT_ERROR = 1  # nothing found / kill failed
EXIT_CANCELLED = 2  # user declined confirmation


def _fail(message: str, code: int = EXIT_ERROR) -> NoReturn:
    err_console.print(message)
    sys.exit(code)


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="portpilot")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """🛫 PortPilot - Interactive Port Manager for Developers

    Run without arguments to open the interactive TUI.
    """
    if ctx.invoked_subcommand is None:
        from .app import PortPilotApp  # imported lazily: Textual is slow to import

        PortPilotApp().run()


@cli.command("list")
@click.option("--port", "-p", type=int, help="Filter by specific port")
@click.option("--name", "-n", help="Filter by process name")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_cmd(port: int | None, name: str | None, as_json: bool) -> None:
    """List all listening ports."""
    connections = filter_connections(get_listening_ports(), port=port, name=name)

    if as_json:
        click.echo(json.dumps(connections, indent=2))
        return

    if not connections:
        console.print("[yellow]No listening ports found matching criteria[/yellow]")
        return

    table = Table(title="🔌 Listening Ports", box=box.ROUNDED, header_style="bold cyan")
    table.add_column("Port", style="green", justify="right")
    table.add_column("IP", style="dim")
    table.add_column("PID", style="yellow")
    table.add_column("Process", style="cyan")
    table.add_column("User", style="magenta")
    table.add_column("Memory", justify="right")

    for conn in connections:
        table.add_row(
            str(conn["port"]),
            conn["ip"],
            str(conn["pid"]),
            conn["name"],
            conn["user"],
            conn["memory"],
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(connections)} listening ports[/dim]")


def _kill_pids(pids: list[int], force: bool, label: str = "") -> bool:
    ok = True
    for pid in pids:
        success, message = kill_process(pid, force=force)
        prefix = f"{label}: " if label else ""
        if success:
            console.print(f"[green]✅ {prefix}{message}[/green]")
        else:
            console.print(f"[red]❌ {prefix}{message}[/red]")
            ok = False
    return ok


@cli.command()
@click.argument("port", type=int)
@click.option("--force", "-f", is_flag=True, help="Force kill (SIGKILL)")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def kill(port: int, force: bool, yes: bool) -> None:
    """Kill process(es) listening on a specific port."""
    matches = filter_connections(get_listening_ports(), port=port)
    if not matches:
        _fail(f"[red]No process found listening on port {port}[/red]")

    pids = killable_pids(matches)
    if not pids:
        _fail(f"[red]Cannot determine PID for port {port} (try elevated privileges)[/red]")

    conn = matches[0]
    console.print(
        Panel(
            f"[bold]Port:[/bold] {conn['port']}\n"
            f"[bold]Process:[/bold] {conn['name']}\n"
            f"[bold]PID:[/bold] {', '.join(map(str, pids))}\n"
            f"[bold]Command:[/bold] {conn['cmdline'][:60]}",
            title="🎯 Target Process",
            border_style="yellow",
        )
    )

    if not yes and not click.confirm("Kill this process?"):
        console.print("[dim]Cancelled[/dim]")
        sys.exit(EXIT_CANCELLED)

    if not _kill_pids(pids, force):
        sys.exit(EXIT_ERROR)


@cli.command()
@click.argument("ports", type=int, nargs=-1, required=True)
@click.option("--force", "-f", is_flag=True, help="Force kill (SIGKILL)")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def killall(ports: tuple[int, ...], force: bool, yes: bool) -> None:
    """Kill processes on multiple ports."""
    connections = get_listening_ports()

    targets: list[tuple[int, PortInfo, list[int]]] = []
    for port in dict.fromkeys(ports):
        matches = filter_connections(connections, port=port)
        pids = killable_pids(matches)
        if pids:
            targets.append((port, matches[0], pids))
        else:
            console.print(f"[yellow]⚠️  No killable process on port {port}[/yellow]")

    if not targets:
        _fail("[red]No valid targets found[/red]")

    table = Table(title="🎯 Targets", box=box.SIMPLE)
    table.add_column("Port")
    table.add_column("Process")
    table.add_column("PID")
    for port, conn, pids in targets:
        table.add_row(str(port), conn["name"], ", ".join(map(str, pids)))
    console.print(table)

    if not yes and not click.confirm(f"Kill {len(targets)} processes?"):
        console.print("[dim]Cancelled[/dim]")
        sys.exit(EXIT_CANCELLED)

    killed: set[int] = set()
    ok = True
    for port, _conn, pids in targets:
        todo = [p for p in pids if p not in killed]  # one process may own several ports
        killed.update(todo)
        ok = _kill_pids(todo, force, label=f"Port {port}") and ok
    if not ok:
        sys.exit(EXIT_ERROR)


@cli.command()
@click.argument("port", type=int)
def info(port: int) -> None:
    """Show detailed info about a port."""
    matches = filter_connections(get_listening_ports(), port=port)
    if not matches:
        _fail(f"[red]No process found listening on port {port}[/red]")

    conn = matches[0]
    addresses = ", ".join(dict.fromkeys(c["ip"] for c in matches))
    console.print(
        Panel(
            f"[bold cyan]Port:[/bold cyan] {conn['port']}\n"
            f"[bold cyan]IP:[/bold cyan] {addresses}\n"
            f"[bold cyan]PID:[/bold cyan] {conn['pid']}\n"
            f"[bold cyan]Process:[/bold cyan] {conn['name']}\n"
            f"[bold cyan]Command:[/bold cyan] {conn['cmdline']}\n"
            f"[bold cyan]User:[/bold cyan] {conn['user']}\n"
            f"[bold cyan]Started:[/bold cyan] {conn['created']}\n"
            f"[bold cyan]Memory:[/bold cyan] {conn['memory']}",
            title=f"🔍 Port {port} Details",
            border_style="cyan",
        )
    )

    if not isinstance(conn["pid"], int):
        return
    try:
        proc = psutil.Process(conn["pid"])
        try:
            files = proc.open_files()[:5]
            if files:
                console.print("\n[bold]Open Files (first 5):[/bold]")
                for f in files:
                    console.print(f"  [dim]{f.path}[/dim]")
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
        try:
            conns = proc.net_connections()
            if conns:
                console.print(f"\n[bold]Total Connections:[/bold] {len(conns)}")
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


def _watch_view(ports: tuple[int, ...]) -> Group:
    connections = get_listening_ports()
    if ports:
        connections = [c for c in connections if c["port"] in ports]

    header = Text.from_markup(
        f"[bold cyan]🔌 Port Watch[/bold cyan] [dim](updated {time.strftime('%H:%M:%S')})[/dim]\n"
    )
    footer = Text.from_markup("\n[dim]Press Ctrl+C to stop[/dim]")
    body: Table | Text
    if not connections:
        body = Text.from_markup("[yellow]No matching ports currently listening[/yellow]")
    else:
        body = Table(box=box.SIMPLE)
        body.add_column("Port", style="green")
        body.add_column("Process", style="cyan")
        body.add_column("PID", style="yellow")
        body.add_column("Memory")
        for conn in connections:
            body.add_row(str(conn["port"]), conn["name"], str(conn["pid"]), conn["memory"])
    return Group(header, body, footer)


@cli.command()
@click.argument("ports", type=int, nargs=-1)
@click.option("--interval", "-i", type=float, default=2.0, show_default=True, help="Seconds")
def watch(ports: tuple[int, ...], interval: float) -> None:
    """Watch specific ports (or all if none specified)."""
    try:
        with Live(_watch_view(ports), console=console, auto_refresh=False) as live:
            while True:
                time.sleep(interval)
                live.update(_watch_view(ports), refresh=True)
    except KeyboardInterrupt:
        console.print("[dim]Stopped watching[/dim]")


def main() -> None:
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
