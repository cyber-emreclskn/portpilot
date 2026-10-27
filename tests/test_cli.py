from __future__ import annotations

import json
from collections.abc import Callable
from importlib.metadata import version

import pytest
from click.testing import CliRunner

from portpilot.cli import EXIT_CANCELLED, EXIT_ERROR, cli

from .conftest import Listener


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_version_matches_package_metadata(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert version("portpilot") in result.output


def test_help_lists_commands(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("list", "kill", "killall", "info", "watch"):
        assert cmd in result.output


# ------------------------------------------------------------------ list


def test_list_json_contains_listener(runner: CliRunner, listener: Listener) -> None:
    result = runner.invoke(cli, ["list", "--json", "-p", str(listener.port)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert [d["pid"] for d in data] == [listener.pid]


def test_list_table(runner: CliRunner, listener: Listener) -> None:
    result = runner.invoke(cli, ["list", "-p", str(listener.port)])
    assert result.exit_code == 0
    assert str(listener.pid) in result.output
    assert "Total: 1" in result.output


def test_list_no_match(runner: CliRunner, free_port: int) -> None:
    result = runner.invoke(cli, ["list", "-p", str(free_port)])
    assert result.exit_code == 0
    assert "No listening ports" in result.output


def test_list_json_no_match_is_empty_array(runner: CliRunner, free_port: int) -> None:
    result = runner.invoke(cli, ["list", "--json", "-p", str(free_port)])
    assert json.loads(result.output) == []


# ------------------------------------------------------------------ kill


def test_kill_with_yes(runner: CliRunner, listener: Listener) -> None:
    result = runner.invoke(cli, ["kill", str(listener.port), "-y"])
    assert result.exit_code == 0, result.output
    assert not listener.is_alive()


def test_kill_confirm_accepted(runner: CliRunner, listener: Listener) -> None:
    result = runner.invoke(cli, ["kill", str(listener.port)], input="y\n")
    assert result.exit_code == 0
    assert not listener.is_alive()


def test_kill_confirm_declined(runner: CliRunner, listener: Listener) -> None:
    result = runner.invoke(cli, ["kill", str(listener.port)], input="n\n")
    assert result.exit_code == EXIT_CANCELLED
    assert listener.is_alive()


def test_kill_nothing_listening_fails(runner: CliRunner, free_port: int) -> None:
    result = runner.invoke(cli, ["kill", str(free_port), "-y"])
    assert result.exit_code == EXIT_ERROR


def test_killall(runner: CliRunner, spawn_listener: Callable[[], Listener]) -> None:
    a, b = spawn_listener(), spawn_listener()
    result = runner.invoke(cli, ["killall", str(a.port), str(b.port), "-y"])
    assert result.exit_code == 0, result.output
    assert not a.is_alive()
    assert not b.is_alive()


def test_killall_partial(runner: CliRunner, listener: Listener, free_port: int) -> None:
    result = runner.invoke(cli, ["killall", str(listener.port), str(free_port), "-y"])
    assert result.exit_code == 0
    assert "No killable process" in result.output
    assert not listener.is_alive()


def test_killall_nothing(runner: CliRunner, free_port: int) -> None:
    result = runner.invoke(cli, ["killall", str(free_port), "-y"])
    assert result.exit_code == EXIT_ERROR


# ------------------------------------------------------------------ info


def test_info(runner: CliRunner, listener: Listener) -> None:
    result = runner.invoke(cli, ["info", str(listener.port)])
    assert result.exit_code == 0
    assert f"Port {listener.port} Details" in result.output
    assert str(listener.pid) in result.output


def test_info_missing(runner: CliRunner, free_port: int) -> None:
    result = runner.invoke(cli, ["info", str(free_port)])
    assert result.exit_code == EXIT_ERROR


# ------------------------------------------------------------------ watch


def test_watch_stops_on_ctrl_c(
    runner: CliRunner, listener: Listener, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupt(_: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("portpilot.cli.time.sleep", interrupt)
    result = runner.invoke(cli, ["watch", str(listener.port)])
    assert result.exit_code == 0
    assert str(listener.port) in result.output
    assert "Stopped watching" in result.output
