"""Smoke tests for the circex CLI."""

from __future__ import annotations

from typer.testing import CliRunner

from circex import __version__
from circex.cli import app

runner = CliRunner()


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "circex" in result.stdout.lower()


def test_version_prints_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_subcommands_are_registered() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("extract", "eval", "serve", "index", "fetch", "version"):
        assert cmd in result.stdout
