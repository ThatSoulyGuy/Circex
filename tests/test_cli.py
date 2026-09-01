"""Smoke tests for the circex CLI."""

from __future__ import annotations

import typer.main
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


def test_label_scaffold_is_registered_and_documented() -> None:
    result = runner.invoke(app, ["label-scaffold", "--help"])
    assert result.exit_code == 0
    # Assert on the declared parameters rather than the rendered help: Rich
    # re-wraps help to the terminal width, so whether a given option name
    # survives as a contiguous substring depends on where the wrap lands.
    command = typer.main.get_command(app).commands["label-scaffold"]
    names = {opt for param in command.params for opt in param.opts}
    # the two inputs a labeler drives it with
    assert {"--circulars", "--extractor"} <= names


def test_post_dry_run_from_file_regex() -> None:
    """`circex post` on the discovery circular emits a source with a parsed position."""
    result = runner.invoke(
        app,
        ["post", "--from-file", "docs/fixtures/grb260604c_44827.json", "--extractor", "regex"],
    )
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert "POST /sources" in result.output
    # coords parser recovers the combined "(RA, Dec) = 14h57m... +28d..." form.
    assert "224.45" in result.output


def test_post_positionless_follow_up_creates_no_source() -> None:
    """A follow-up with no RA/Dec must NOT emit a source-create (SkyPortal would 400)."""
    result = runner.invoke(
        app,
        ["post", "--from-file", "docs/fixtures/grb260604c_44877.json", "--extractor", "regex"],
    )
    assert result.exit_code == 0, result.output
    assert "source=no" in result.output
    assert "POST /sources" not in result.output


def test_post_requires_a_source() -> None:
    result = runner.invoke(app, ["post", "--extractor", "regex"])
    assert result.exit_code != 0


def test_event_aggregates_fixtures_dry_run() -> None:
    """`circex event --circulars-dir` fuses the fixtures into one source (dry-run)."""
    result = runner.invoke(
        app,
        [
            "event",
            "--circulars-dir",
            "docs/fixtures",
            "--extractor",
            "regex",
            "--default-instrument-id",
            "4",
            "--group-ids",
            "1988",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert "source=GRB260604C" in result.output
    assert "POST /sources" in result.output
