from __future__ import annotations

import json
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console

from circex import __version__
from circex.schema import CircularExtraction
from circex.schema.dump import write_all

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


@app.command(name="schema-dump")
def schema_dump(
    out: Path = typer.Option(Path("schemas/"), "--out", help="output directory"),
) -> None:
    """Dump Pydantic models to JSON Schema files for the upstream gcn-schema PR."""
    written = write_all(out)
    for path in written:
        console.print(f"[green]wrote[/] {path}")


@app.command(name="label-validate")
def label_validate(
    target: Path = typer.Argument(
        ..., help="Either a single .label.json file or a directory of them"
    ),
) -> None:
    """Validate hand-labeled circulars against the CircularExtraction Pydantic model."""
    if target.is_file():
        paths = [target]
    elif target.is_dir():
        paths = sorted(target.rglob("*.label.json"))
    else:
        console.print(f"[red]error:[/] no such file or directory: {target}")
        raise typer.Exit(code=2)

    if not paths:
        console.print(f"[yellow]no label files found under {target}[/]")
        raise typer.Exit(code=1)

    errors = 0
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            CircularExtraction.model_validate(payload)
            console.print(f"[green]OK[/] {path}")
        except ValidationError as exc:
            errors += 1
            console.print(f"[red]INVALID[/] {path}")
            for err in exc.errors():
                console.print(f"    {err['loc']}: {err['msg']}")
        except json.JSONDecodeError as exc:
            errors += 1
            console.print(f"[red]MALFORMED JSON[/] {path}: {exc}")

    if errors:
        console.print(f"[red]{errors} of {len(paths)} files failed validation[/]")
        raise typer.Exit(code=1)
    console.print(f"[green]All {len(paths)} files valid.[/]")


@app.command(name="subset-build")
def subset_build(
    per_stratum: int = typer.Option(100, "--per-stratum"),
    max_optical: int = typer.Option(5000, "--max-optical", help="cap on optical pool for speed"),
    seed: int = typer.Option(42, "--seed"),
    out: Path = typer.Option(
        Path("data/subsets/optical_iter_v1.json"), "--out"
    ),
) -> None:
    """Untar the archive, filter to optical, and build a stratified iteration subset."""
    from circex.data.archive import iter_circulars, untar_archive
    from circex.data.subset import build_stratified_subset, save_subset
    from circex.data.topics import load_optical_ids

    untar_archive()
    optical_ids = sorted(load_optical_ids())[:max_optical]
    records = list(iter_circulars(circular_ids=optical_ids))
    subset = build_stratified_subset(records, per_stratum=per_stratum, seed=seed)
    save_subset(subset, out)
    console.print(f"[green]wrote {len(subset)} stratified circulars to {out}[/]")


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
