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


def test_post_dry_run_from_file_regex() -> None:
    """`circex post` extracts a circular from a file and prints a SkyPortal plan."""
    result = runner.invoke(
        app,
        ["post", "--from-file", "docs/fixtures/grb260604c_44877.json", "--extractor", "regex"],
    )
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert "POST /sources" in result.output
    # regex can't time the seed's table row -> it's a comment, not a photometry post.
    assert "could not be posted" in result.output


def test_post_requires_a_source() -> None:
    result = runner.invoke(app, ["post", "--extractor", "regex"])
    assert result.exit_code != 0
