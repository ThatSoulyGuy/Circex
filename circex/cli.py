from __future__ import annotations

import typer
from rich.console import Console

from circex import __version__

app = typer.Typer(
    name="circex",
    help="LLM-based extractor for GCN optical circulars.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Print the installed circex version."""
    console.print(f"circex {__version__}")


@app.command()
def extract(
    extractor: str = typer.Option(
        ..., "--extractor", help="regex | claude-haiku | claude-sonnet | ollama"
    ),
    circulars: str = typer.Option(
        ..., "--circulars", help="path to a circulars subset JSON or label dir"
    ),
    out: str = typer.Option(..., "--out", help="output directory for extraction results"),
) -> None:
    """Run an extractor over a set of circulars. (Sprint 2+)"""
    console.print(f"[yellow]not yet implemented[/]: extract {extractor=} {circulars=} {out=}")
    raise typer.Exit(code=2)


@app.command()
def eval(
    extractors: str = typer.Option("all", "--extractors"),
    gold: str = typer.Option(..., "--gold"),
    report: str = typer.Option("reports/eval_v1.md", "--report"),
) -> None:
    """Run the four-way evaluation harness. (Sprint 4)"""
    console.print(f"[yellow]not yet implemented[/]: eval {extractors=} {gold=} {report=}")
    raise typer.Exit(code=2)


@app.command()
def serve(
    worker: bool = typer.Option(False, "--worker"),
    ingest: bool = typer.Option(False, "--ingest"),
) -> None:
    """Run the long-lived Python worker or the ingestion daemon. (Sprint 5)"""
    console.print(f"[yellow]not yet implemented[/]: serve {worker=} {ingest=}")
    raise typer.Exit(code=2)


@app.command()
def index(
    backfill: bool = typer.Option(False, "--backfill"),
    max_cost: float = typer.Option(0.0, "--max-cost"),
) -> None:
    """Index circulars into the SQLite database; optionally backfill extractions. (Sprint 5)"""
    console.print(f"[yellow]not yet implemented[/]: index {backfill=} {max_cost=}")
    raise typer.Exit(code=2)


@app.command()
def fetch(
    since: int = typer.Option(0, "--since", help="lowest circular id to fetch"),
) -> None:
    """Fetch new GCN circulars from gcn.nasa.gov. (Sprint 5)"""
    console.print(f"[yellow]not yet implemented[/]: fetch {since=}")
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
