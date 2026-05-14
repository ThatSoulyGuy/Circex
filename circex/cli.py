from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from pydantic import ValidationError
from rich.console import Console

from circex import __version__
from circex.schema import CircularExtraction
from circex.schema.dump import write_all

if TYPE_CHECKING:
    from circex.extract.protocol import Extractor

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


_CLAUDE_MODEL_IDS = {
    "claude-haiku": "claude-haiku-4-5-20251001",
    "claude-sonnet": "claude-sonnet-4-6",
}


def _build_extractor(
    name: str, cache_path: Path | None
) -> Extractor:
    """Resolve an extractor name to an instance. Lazy imports so the CLI loads even
    when the LLM clients aren't usable yet (e.g., missing API keys)."""
    if name == "regex":
        from circex.extract.regex import RegexExtractor
        return RegexExtractor()

    from circex.cache.llm import LLMCache
    cache = LLMCache(cache_path) if cache_path is not None else None

    if name in _CLAUDE_MODEL_IDS:
        from circex.extract.llm import ClaudeExtractor
        return ClaudeExtractor(model_id=_CLAUDE_MODEL_IDS[name], cache=cache)
    if name == "ollama":
        from circex.extract.llm import OllamaExtractor
        return OllamaExtractor(cache=cache)
    raise typer.BadParameter(
        f"unknown extractor {name!r}; choose regex | claude-haiku | claude-sonnet | ollama"
    )


@app.command()
def extract(
    extractor: str = typer.Option(
        "regex", "--extractor",
        help="regex | claude-haiku | claude-sonnet | ollama",
    ),
    circulars: Path = typer.Option(
        ..., "--circulars", help="path to a subset.json or a directory of *.label.json files"
    ),
    out: Path = typer.Option(..., "--out", help="output directory for extraction results"),
    cache_db: Path = typer.Option(
        Path("data/cache/llm.sqlite"), "--cache-db",
        help="SQLite cache file for LLM responses",
    ),
) -> None:
    """Run an extractor over a set of circulars and write CircularExtraction JSON files."""
    from circex.data.archive import iter_circulars
    from circex.data.subset import load_subset
    from circex.extract.protocol import Circular

    ids: list[int] = []
    if circulars.is_file() and circulars.suffix == ".json":
        ids = [s.circular_id for s in load_subset(circulars)]
    elif circulars.is_dir():
        ids = sorted(int(p.stem.split(".")[0]) for p in circulars.glob("*.label.json"))
    else:
        console.print(f"[red]error:[/] {circulars} is not a subset.json or label dir")
        raise typer.Exit(code=2)

    if not ids:
        console.print(f"[yellow]no circulars found in {circulars}[/]")
        raise typer.Exit(code=1)

    out.mkdir(parents=True, exist_ok=True)
    ext = _build_extractor(extractor, cache_db if extractor != "regex" else None)
    records = {int(r["circularId"]): r for r in iter_circulars(circular_ids=ids)}

    written = 0
    missing = 0
    for cid in ids:
        rec = records.get(cid)
        if rec is None:
            missing += 1
            continue
        result = ext.extract(Circular.from_record(rec))
        out_path = out / f"{cid:06d}.extraction.json"
        out_path.write_text(
            result.model_dump_json(indent=2, by_alias=True, exclude_none=True) + "\n",
            encoding="utf-8",
        )
        written += 1

    console.print(
        f"[green]wrote {written} extractions to {out}[/]"
        + (f" ([yellow]{missing} circulars missing from archive[/])" if missing else "")
    )


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


@app.command(name="eval")
def eval_cmd(
    extractors: str = typer.Option(
        "regex",
        "--extractors",
        help="Comma-separated: regex,claude-haiku,claude-sonnet,ollama. 'all' = all four.",
    ),
    gold: str = typer.Option(
        "vidushi", "--gold", help="vidushi | path/to/labels/dir"
    ),
    report: Path = typer.Option(Path("reports/eval_v1.md"), "--report"),
    max_circulars: int = typer.Option(
        500, "--max-circulars",
        help="Cap to keep API costs bounded for vidushi-gold runs.",
    ),
    cache_db: Path = typer.Option(Path("data/cache/llm.sqlite"), "--cache-db"),
    seed: int = typer.Option(42, "--seed"),
) -> None:
    """Run the four-way evaluation harness against gold and emit a markdown report."""
    from circex.data.archive import iter_circulars
    from circex.eval.report import (
        ExtractorReport,
        evaluate_extractor,
        write_report,
    )
    from circex.eval.runner import run_extractor
    from circex.eval.vidushi_adapter import load_vidushi_eval
    from circex.extract.protocol import Circular

    # ---- resolve gold + which circulars to evaluate ----
    if gold == "vidushi":
        eval_set = load_vidushi_eval()
        gold_extractions = eval_set.gold[:max_circulars]
        rng = __import__("random").Random(seed)
        sampled_rows = eval_set.rows[:max_circulars]
        ids = [r.circular_id for r in sampled_rows]
        records = {int(r["circularId"]): r for r in iter_circulars(circular_ids=ids)}
        circulars = [
            Circular.from_record(records[cid])
            for cid in ids
            if cid in records
        ]
        # Trim gold to circulars we actually loaded.
        loaded_ids = {c.circular_id for c in circulars}
        gold_extractions = [g for g in gold_extractions if g.circular_id in loaded_ids]
        vidushi_pred = [
            p for p in eval_set.predicted[:max_circulars] if p.circular_id in loaded_ids
        ]
        del rng
    else:
        # Hand-label gold dir.
        gold_dir = Path(gold)
        if not gold_dir.is_dir():
            console.print(f"[red]error:[/] {gold!r} is not 'vidushi' or a directory")
            raise typer.Exit(code=2)
        gold_extractions = []
        for path in sorted(gold_dir.glob("*.label.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            gold_extractions.append(CircularExtraction.model_validate(payload))
        ids = [g.circular_id for g in gold_extractions]
        records = {int(r["circularId"]): r for r in iter_circulars(circular_ids=ids)}
        circulars = [
            Circular.from_record(records[g.circular_id])
            for g in gold_extractions
            if g.circular_id in records
        ]
        vidushi_pred = []

    if not circulars:
        console.print("[red]error:[/] no circulars available to evaluate")
        raise typer.Exit(code=2)

    # ---- resolve extractor list ----
    if extractors == "all":
        extractor_names = ["regex", "claude-haiku", "claude-sonnet", "ollama"]
    else:
        extractor_names = [e.strip() for e in extractors.split(",")]

    reports: list[ExtractorReport] = []

    for name in extractor_names:
        try:
            ext = _build_extractor(name, cache_db if name != "regex" else None)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[yellow]skipping {name}: {exc}[/]")
            continue

        console.print(f"[blue]running {name} on {len(circulars)} circulars…[/]")
        results, stats = run_extractor(ext, circulars)
        console.print(
            f"  {stats.n_succeeded}/{stats.n_total} OK, "
            f"cost=${stats.cost_usd:.4f}, failed={stats.n_failed}"
        )
        reports.append(
            evaluate_extractor(ext.extractor_id, results, gold_extractions)
        )

    # Add Vidushi-predicted column for the Vidushi-gold case.
    if vidushi_pred:
        reports.append(evaluate_extractor("vidushi-mistral", vidushi_pred, gold_extractions))

    write_report(reports, report)
    console.print(f"[green]wrote {report}[/]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    store_path: Path = typer.Option(
        Path("data/extractions.sqlite"), "--store",
        help="SQLite file backing the extraction store.",
    ),
    db_path: Path = typer.Option(
        Path("data/circex.sqlite"), "--db",
        help="SQLite FTS5 file for search_gcn_circulars.",
    ),
    default_extractor: str = typer.Option(
        "regex", "--extractor",
        help="On-the-fly extractor for extract_properties cache misses.",
    ),
    cache_db: Path = typer.Option(Path("data/cache/llm.sqlite"), "--cache-db"),
) -> None:
    """Run the long-lived Python worker (TCP). The TS LeanMCP bridge talks to it."""
    import asyncio as _asyncio

    from circex.server.worker import serve as _serve

    extractor = (
        _build_extractor(default_extractor, cache_db if default_extractor != "regex" else None)
        if default_extractor
        else None
    )
    console.print(
        f"[green]starting worker on {host}:{port}[/] "
        f"(store={store_path}, extractor={default_extractor})"
    )
    try:
        _asyncio.run(_serve(
            store_path=store_path,
            host=host,
            port=port,
            db_path=db_path if db_path.exists() else None,
            default_extractor=extractor,
        ))
    except KeyboardInterrupt:
        console.print("[yellow]worker stopped[/]")


@app.command()
def index(
    circulars: Path = typer.Option(
        Path("data/labels/hand_v1"), "--circulars",
        help="subset.json or directory of *.label.json files to backfill from",
    ),
    extractor: str = typer.Option("regex", "--extractor"),
    store_path: Path = typer.Option(Path("data/extractions.sqlite"), "--store"),
    cache_db: Path = typer.Option(Path("data/cache/llm.sqlite"), "--cache-db"),
    backfill: bool = typer.Option(
        True, "--backfill/--no-backfill",
        help="Run the extractor on every circular and persist to the extraction store.",
    ),
    max_cost: float = typer.Option(10.0, "--max-cost"),
) -> None:
    """Backfill the extraction store: walks circulars, extracts, persists."""
    from circex.data.archive import iter_circulars
    from circex.data.subset import load_subset
    from circex.eval.runner import run_extractor
    from circex.extract.protocol import Circular
    from circex.server.store import ExtractionStore

    if not backfill:
        console.print("[yellow]--no-backfill given; nothing to do[/]")
        raise typer.Exit(code=0)

    if circulars.is_file() and circulars.suffix == ".json":
        ids = [s.circular_id for s in load_subset(circulars)]
    elif circulars.is_dir():
        ids = sorted(int(p.stem.split(".")[0]) for p in circulars.glob("*.label.json"))
    else:
        console.print(f"[red]error:[/] {circulars} is not a subset.json or label dir")
        raise typer.Exit(code=2)

    ext = _build_extractor(extractor, cache_db if extractor != "regex" else None)
    records = {int(r["circularId"]): r for r in iter_circulars(circular_ids=ids)}
    inputs = [Circular.from_record(records[cid]) for cid in ids if cid in records]

    console.print(
        f"[blue]indexing {len(inputs)} circulars with {extractor} (max_cost=${max_cost})[/]"
    )
    results, stats = run_extractor(ext, inputs, max_usd=max_cost)
    with ExtractionStore(store_path) as store:
        for result in results:
            store.put(result)
    console.print(
        f"[green]persisted {len(results)}/{stats.n_total} extractions to {store_path}[/] "
        f"(cost=${stats.cost_usd:.4f}, failed={stats.n_failed})"
    )


@app.command()
def fetch(
    since: int = typer.Option(0, "--since", help="lowest circular id to fetch"),
) -> None:
    """Fetch new GCN circulars from gcn.nasa.gov. (Sprint 5)"""
    console.print(f"[yellow]not yet implemented[/]: fetch {since=}")
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
