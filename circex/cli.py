from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    circulars_dir: Path | None = typer.Option(
        None, "--circulars-dir",
        help="dir of {id}.json bodies for label-dir gold not in the local archive",
    ),
    report: Path = typer.Option(Path("reports/eval_v1.md"), "--report"),
    plot: Path | None = typer.Option(
        None, "--plot",
        help="Optional PNG path; writes a 2-panel F1 + Δ-vs-baseline figure.",
    ),
    plot_baseline: str = typer.Option(
        "regex-v1", "--plot-baseline",
        help="Extractor ID to use as the baseline in the Δ panel.",
    ),
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
        if circulars_dir is not None:
            records = {}
            for cid in ids:
                path = circulars_dir / f"{cid}.json"
                if path.exists():
                    records[cid] = json.loads(path.read_text(encoding="utf-8"))
        else:
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

    if plot is not None:
        from circex.eval.plot import plot_eval
        try:
            n = len(circulars)
            title = f"gold={gold}, n={n}"
            plot_eval(reports, plot, baseline_id=plot_baseline, title_suffix=title)
            console.print(f"[green]wrote {plot}[/]")
        except ImportError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(code=2) from exc


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
def post(
    circular_id: int = typer.Option(
        0, "--circular-id", help="GCN circular id to fetch from the local archive"
    ),
    from_file: Path | None = typer.Option(
        None, "--from-file", help="raw circular JSON (a Kafka message / fixture) instead of an id"
    ),
    extractor: str = typer.Option(
        "ollama", "--extractor", help="regex | claude-haiku | claude-sonnet | ollama"
    ),
    trigger_time: str | None = typer.Option(
        None, "--trigger-time", help="event T0 (ISO-8601) for resolving relative offsets"
    ),
    instrument_map: Path | None = typer.Option(
        None, "--instrument-map", help="JSON {telescope_canonical: skyportal_instrument_id}"
    ),
    default_instrument_id: int | None = typer.Option(
        None, "--default-instrument-id",
        help="generic GCN instrument id for unmapped telescopes (SkyPortal requires one)",
    ),
    group_ids: str = typer.Option("", "--group-ids", help="comma-separated SkyPortal group ids"),
    live: bool = typer.Option(
        False, "--live", help="actually POST to SkyPortal (needs --token/--url); default dry-run"
    ),
    url: str = typer.Option("", "--url", help="SkyPortal API base URL (with --live)"),
    token: str = typer.Option("", "--token", help="SkyPortal token (with --live)"),
    cache_db: Path = typer.Option(Path("data/cache/llm.sqlite"), "--cache-db"),
) -> None:
    """Extract one circular and map it to SkyPortal writes (dry-run by default).

    Examples:
      circex post --from-file docs/fixtures/grb260604c_44877.json --extractor ollama
      circex post --circular-id 44877 --extractor regex
      circex post --from-file msg.json --extractor claude-haiku --live --url ... --token ...
    """

    from circex.bot import to_actions
    from circex.bot.poster import SkyPortalPoster, render_plan
    from circex.extract.protocol import Circular

    # ---- load the circular ----
    if from_file is not None:
        record = json.loads(from_file.read_text(encoding="utf-8"))
    elif circular_id:
        from circex.data.archive import iter_circulars

        records = list(iter_circulars(circular_ids=[circular_id]))
        if not records:
            console.print(f"[red]circular {circular_id} not found in the local archive[/]")
            raise typer.Exit(code=2)
        record = records[0]
    else:
        raise typer.BadParameter("pass --circular-id or --from-file")

    t0 = None
    if trigger_time is not None:
        from dateutil import parser as _dp

        t0 = _dp.parse(trigger_time)
    circular = Circular(
        circular_id=int(record.get("circularId", circular_id) or 0),
        subject=str(record.get("subject") or ""),
        body=str(record.get("body") or ""),
        event_id=record.get("eventId") or None,
        trigger_time=t0,
    )

    # ---- extract ----
    cache = cache_db if extractor != "regex" else None
    extraction = _build_extractor(extractor, cache).extract(circular)

    # ---- map to SkyPortal actions ----
    imap: dict[str, int] = {}
    if instrument_map is not None:
        imap = {k: int(v) for k, v in json.loads(instrument_map.read_text()).items()}
    gids = [int(g) for g in group_ids.split(",") if g.strip()]
    actions = to_actions(
        extraction,
        instrument_map=imap,
        default_instrument_id=default_instrument_id,
        group_ids=gids,
    )

    poster = SkyPortalPoster(
        base_url=url or "https://skyportal.example/api",
        token=token or None,
        live=live,
    )
    plan = poster.post(actions)

    mode = "LIVE POST" if (live and token) else "DRY-RUN (nothing sent)"
    console.print(f"\n[bold]circex post — {mode}[/]")
    console.print(
        f"extractor={extractor}  circular={circular.circular_id}  "
        f"source={'yes' if actions.source else 'no'}  "
        f"photometry={len(actions.photometry)}  "
        f"redshift={'yes' if actions.redshift else 'no'}  "
        f"comments={len(actions.comments)}  skipped_rows={actions.skipped_rows}\n"
    )
    console.print(render_plan(plan) or "(no actions)")


@app.command()
def event(
    seed: int = typer.Option(
        0, "--seed", help="a circular id; walks its GCN cross-references to gather the event"
    ),
    circulars_dir: Path | None = typer.Option(
        None, "--circulars-dir", help="folder of raw circular JSONs (one event) instead of --seed"
    ),
    circular_ids: str = typer.Option(
        "", "--circular-ids", help="explicit comma-separated circular ids to fetch"
    ),
    max_hops: int = typer.Option(1, "--max-hops", help="cross-reference walk depth for --seed"),
    event_name: str = typer.Option("", "--event-name", help="override the source name"),
    extractor: str = typer.Option("regex", "--extractor", help="regex | claude-haiku | ollama"),
    trigger_time: str | None = typer.Option(
        None, "--trigger-time", help="event T0 (ISO-8601) for resolving relative offsets"
    ),
    instrument_map: Path | None = typer.Option(
        None, "--instrument-map", help="JSON {telescope_canonical: skyportal_instrument_id}"
    ),
    default_instrument_id: int | None = typer.Option(
        None, "--default-instrument-id", help="generic instrument id for unmapped telescopes"
    ),
    group_ids: str = typer.Option("", "--group-ids", help="comma-separated SkyPortal group ids"),
    live: bool = typer.Option(False, "--live", help="actually POST to SkyPortal; default dry-run"),
    url: str = typer.Option("", "--url", help="SkyPortal API base URL (with --live)"),
    token: str = typer.Option("", "--token", help="SkyPortal token (with --live)"),
    cache_db: Path = typer.Option(Path("data/cache/llm.sqlite"), "--cache-db"),
) -> None:
    """Aggregate one event's circulars into a single SkyPortal source (dry-run by default).

    Examples:
      circex event --seed 44877 --extractor regex --default-instrument-id 4
      circex event --circulars-dir flurry/ --group-ids 1988 --live --url ... --token ...
    """
    import json as _json

    from circex.bot import aggregate_event, gather_by_xref
    from circex.bot.poster import SkyPortalPoster, render_plan
    from circex.fetch.gcn_poller import fetch_circular

    def _fetch(cid: int) -> dict[str, Any] | None:
        text = fetch_circular(cid)
        if text is None:
            return None
        d = _json.loads(text)
        return {
            "circularId": d.get("circularId", cid),
            "subject": d.get("subject", ""),
            "body": d.get("body", ""),
            "eventId": d.get("eventId"),
        }

    # ---- gather the event's circulars ----
    if circulars_dir is not None:
        records = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(circulars_dir.glob("*.json"))
        ]
    elif seed:
        records = gather_by_xref(seed, _fetch, max_hops=max_hops)
    elif circular_ids:
        records = [
            r for cid in circular_ids.split(",") if (r := _fetch(int(cid.strip()))) is not None
        ]
    else:
        raise typer.BadParameter("pass --seed, --circulars-dir, or --circular-ids")

    if not records:
        console.print("[red]no circulars gathered[/]")
        raise typer.Exit(code=2)

    t0 = None
    if trigger_time is not None:
        from dateutil import parser as _dp

        t0 = _dp.parse(trigger_time)

    imap: dict[str, int] = {}
    if instrument_map is not None:
        imap = {k: int(v) for k, v in json.loads(instrument_map.read_text()).items()}
    gids = [int(g) for g in group_ids.split(",") if g.strip()]
    cache = cache_db if extractor != "regex" else None

    actions = aggregate_event(
        records,
        _build_extractor(extractor, cache),
        trigger_time=t0,
        instrument_map=imap,
        default_instrument_id=default_instrument_id,
        group_ids=gids,
        event_name=event_name or None,
    )

    poster = SkyPortalPoster(
        base_url=url or "https://skyportal.example/api", token=token or None, live=live
    )
    plan = poster.post(actions)

    mode = "LIVE POST" if (live and token) else "DRY-RUN (nothing sent)"
    src = actions.source
    console.print(f"\n[bold]circex event — {mode}[/]")
    console.print(
        f"circulars={len(records)}  extractor={extractor}  "
        f"source={src.id if src else 'NONE (no position found)'}  "
        f"photometry={len(actions.photometry)}  redshift={'yes' if actions.redshift else 'no'}  "
        f"comments={len(actions.comments)}  skipped_rows={actions.skipped_rows}\n"
    )
    console.print(render_plan(plan) or "(no actions)")


@app.command()
def dataset(
    source: str = typer.Option("vidushi", "--source", help="vidushi | path/to/labels/dir"),
    out: Path = typer.Option(Path("data/finetune"), "--out", help="output dir for train/val jsonl"),
    max_examples: int = typer.Option(0, "--max", help="cap number of examples (0 = all)"),
    val_every: int = typer.Option(10, "--val-every", help="hold out every Nth example for val"),
) -> None:
    """Build a Mistral instruction-tuning dataset (chat JSONL) from labeled circulars.

    Examples:
      circex dataset --source vidushi --out data/finetune
      circex dataset --source data/labels/hand_v1 --out data/finetune_labels
    """
    import itertools

    from circex.train import label_dir_examples, vidushi_examples, write_jsonl

    if source == "vidushi":
        from circex.eval.vidushi_adapter import load_vidushi_eval

        examples = vidushi_examples(load_vidushi_eval().rows)
    else:
        from circex.data.archive import iter_circulars

        def _body(cid: int) -> str | None:
            # Prefer a body co-located with the labels (labels_dir/sources/{id}.json),
            # so a label set for circulars outside the local archive is self-contained.
            local = Path(source) / "sources" / f"{cid}.json"
            if local.exists():
                return str(json.loads(local.read_text(encoding="utf-8")).get("body"))
            recs = list(iter_circulars(circular_ids=[cid]))
            return str(recs[0].get("body")) if recs else None

        examples = label_dir_examples(Path(source), _body)

    if max_examples:
        examples = itertools.islice(examples, max_examples)
    n_train, n_val = write_jsonl(examples, out, val_every=val_every)
    console.print(f"[green]wrote {n_train} train + {n_val} val examples to {out}/[/]")


@app.command(name="classify-train")
def classify_train(
    archive: Path = typer.Option(
        Path("data/archive_2025/archive.json"), "--archive", help="dir of circular JSONs"
    ),
    out: Path = typer.Option(Path("data/models/sn_type.json"), "--out", help="model output path"),
    none_ratio: int = typer.Option(6, "--none-ratio", help="NONE examples per positive"),
    gold: Path | None = typer.Option(
        Path("data/labels/spec_v1"), "--gold", help="label dir to score classification on"
    ),
) -> None:
    """Train the SN-type Naive Bayes classifier from harvested archive labels.

    The final model trains on ALL harvested silver labels (the hand gold, held out
    from training, is the generalization test reported below).
    """
    from circex.classify import SNTypeClassifier, harvest_training_data
    from circex.extract.protocol import Circular
    from circex.extract.regex import RegexExtractor

    gold_ids: set[int] = set()
    if gold is not None and gold.is_dir():
        gold_ids = {int(p.stem.split(".")[0]) for p in gold.glob("*.label.json")}
    data = harvest_training_data(archive, none_ratio=none_ratio, exclude_ids=gold_ids)
    clf = SNTypeClassifier.fit([t for t, _ in data], [lab for _, lab in data])
    clf.save(out)
    console.print(f"[green]trained on {len(data)} examples[/] ({len(gold_ids)} gold held out)")
    console.print(f"model -> {out}  (classes: {', '.join(clf.classes)})\n")

    if not gold_ids:
        return

    # Score the classification field on the hand gold — NB vs regex, same circulars.
    def _f1(pairs: list[tuple[str | None, str | None]]) -> tuple[float, float, float]:
        tp = sum(1 for g, p in pairs if g and p and g == p)
        fp = sum(1 for g, p in pairs if p and g != p)
        fn = sum(1 for g, p in pairs if g and g != p)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        return prec, rec, f1

    assert gold is not None  # gold_ids is only populated when gold is a directory
    regex = RegexExtractor()
    nb_pairs: list[tuple[str | None, str | None]] = []
    rx_pairs: list[tuple[str | None, str | None]] = []
    for label_path in sorted(gold.glob("*.label.json")):
        cid = int(label_path.stem.split(".")[0])
        gold_ext = CircularExtraction.model_validate_json(label_path.read_text(encoding="utf-8"))
        gold_type = gold_ext.classification.classification if gold_ext.classification else None
        body = json.loads((gold / "sources" / f"{cid}.json").read_text())
        subject, text_body = body.get("subject", ""), body.get("body", "")
        nb_pairs.append((gold_type, clf.predict_type(f"{subject}\n{text_body}")))
        rx = regex.extract(Circular(circular_id=cid, subject=subject, body=text_body))
        rx_type = rx.classification.classification if rx.classification else None
        rx_pairs.append((gold_type, rx_type))
    np_, nr, nf = _f1(nb_pairs)
    rp, rr, rf = _f1(rx_pairs)
    console.print(f"[bold]classification F1 on {gold.name} gold:[/]")
    console.print(f"  Naive Bayes : F1 {nf:.3f}  (P {np_:.3f} / R {nr:.3f})")
    console.print(f"  regex       : F1 {rf:.3f}  (P {rp:.3f} / R {rr:.3f})")


@app.command()
def consume(
    from_dir: Path | None = typer.Option(
        None, "--from-dir", help="replay circulars from a dir of {id}.json (test/demo)"
    ),
    kafka: bool = typer.Option(
        False, "--kafka", help="consume live from GCN Kafka (needs GCN_CLIENT_ID/SECRET env)"
    ),
    model: Path | None = typer.Option(
        None, "--model", help="SN-type classifier model for the classification field"
    ),
    default_instrument_id: int | None = typer.Option(None, "--default-instrument-id"),
    instrument_map: Path | None = typer.Option(None, "--instrument-map"),
    group_ids: str = typer.Option("", "--group-ids", help="comma-separated SkyPortal group ids"),
    live: bool = typer.Option(False, "--live", help="actually POST to SkyPortal; default dry-run"),
    url: str = typer.Option("", "--url"),
    token: str = typer.Option("", "--token"),
) -> None:
    """Process every incoming GCN circular into SkyPortal (dry-run by default).

    Examples:
      circex consume --from-dir flurry/ --model data/models/sn_type.json --default-instrument-id 4
      circex consume --kafka --live --url ... --token ... --group-ids 1988
    """
    from circex.bot.poster import SkyPortalPoster
    from circex.consume import dir_fetch, gcn_kafka_records, replay_dir_records, run
    from circex.extract.regex import RegexExtractor
    from circex.fetch.gcn_poller import fetch_circular

    clf = None
    if model is not None:
        from circex.classify import SNTypeClassifier

        clf = SNTypeClassifier.load(model)
    extractor = RegexExtractor(sn_classifier=clf)
    gids = [int(g) for g in group_ids.split(",") if g.strip()]
    imap: dict[str, int] = {}
    if instrument_map is not None:
        imap = {k: int(v) for k, v in json.loads(instrument_map.read_text()).items()}
    poster = SkyPortalPoster(
        base_url=url or "https://skyportal.example/api", token=token or None, live=live,
        continue_on_error=True,  # unattended: a single bad POST must not kill the stream
    )

    if from_dir is not None:
        records = replay_dir_records(from_dir)
        fetch = dir_fetch(from_dir)
    elif kafka:
        client_id, secret = os.environ.get("GCN_CLIENT_ID"), os.environ.get("GCN_CLIENT_SECRET")
        if not (client_id and secret):
            raise typer.BadParameter("set GCN_CLIENT_ID and GCN_CLIENT_SECRET for --kafka")
        records = gcn_kafka_records(client_id, secret)

        def fetch(cid: int) -> dict[str, Any] | None:
            text = fetch_circular(cid)
            return json.loads(text) if text else None
    else:
        raise typer.BadParameter("pass --from-dir or --kafka")

    prime = None
    if live and token and url:
        import requests

        def prime(obj_id: str) -> list[tuple[str, str, float]]:
            resp = requests.get(
                f"{url.rstrip('/')}/sources/{obj_id}/photometry",
                headers={"Authorization": f"token {token}"},
                timeout=30,
            )
            pts = resp.json().get("data", []) if resp.status_code < 400 else []
            return [
                (obj_id, p.get("filter"), p.get("mjd"))
                for p in pts
                if p.get("filter") and p.get("mjd") is not None
            ]

    mode = "LIVE POST" if (live and token) else "DRY-RUN (nothing sent)"
    tag = "regex+classifier" if clf else "regex"
    console.print(f"\n[bold]circex consume — {mode}[/]  (extractor: {tag})\n")

    def report(result: Any) -> None:
        if result.status == "posted":
            console.print(
                f"  GCN {result.circular_id} -> {result.obj_id}: "
                f"+{result.photometry_posted} photometry "
                f"({result.photometry_skipped} already present)"
            )
        else:
            console.print(f"  GCN {result.circular_id}: {result.status}")

    run(
        records,
        extractor=extractor,
        poster=poster,
        fetch=fetch,
        group_ids=gids,
        instrument_map=imap,
        default_instrument_id=default_instrument_id,
        prime=prime,
        on_result=report,
    )


@app.command()
def annotate(
    from_file: Path | None = typer.Option(
        None, "--from-file", help="one raw circular JSON to annotate"
    ),
    circulars_dir: Path | None = typer.Option(
        None, "--circulars-dir", help="folder of raw circular JSONs (batch mode)"
    ),
    extractor: str = typer.Option(
        "regex", "--extractor", help="regex | claude-haiku | claude-sonnet | ollama"
    ),
    out: Path | None = typer.Option(
        None, "--out", help="output file (single) or directory (batch); stdout if omitted"
    ),
    cache_db: Path = typer.Option(Path("data/cache/llm.sqlite"), "--cache-db"),
) -> None:
    """Emit a flat {field: {value, snippet, start, end}} map per circular.

    For snippet-level human validation: every extracted value is paired with the
    source-text snippet it came from. Single circular to stdout, or batch a
    folder into `<out>/<circular_id>.json` (the layout gcn-nlp-label expects).

      circex annotate --from-file docs/fixtures/grb260604c_44877.json
      circex annotate --circulars-dir circulars/ --extractor ollama --out extracted_circulars/
    """
    from circex.extract.protocol import Circular
    from circex.label import to_label_fields

    def _annotate_record(record: dict[str, object]) -> tuple[int, str]:
        circ = Circular(
            circular_id=int(str(record.get("circularId") or 0)),
            subject=str(record.get("subject") or ""),
            body=str(record.get("body") or ""),
            event_id=record.get("eventId") or None,  # type: ignore[arg-type]
        )
        ext = _build_extractor(extractor, cache_db if extractor != "regex" else None)
        fields = to_label_fields(ext.extract(circ))
        return circ.circular_id, json.dumps(fields, indent=2, ensure_ascii=False) + "\n"

    if from_file is not None:
        _, text = _annotate_record(json.loads(from_file.read_text(encoding="utf-8")))
        if out is not None:
            out.write_text(text, encoding="utf-8")
            console.print(f"[green]wrote[/] {out}")
        else:
            console.print(text)
    elif circulars_dir is not None:
        if out is None:
            console.print("[red]--out <dir> is required in batch mode[/]")
            raise typer.Exit(code=2)
        out.mkdir(parents=True, exist_ok=True)
        n = 0
        for src in sorted(circulars_dir.glob("*.json")):
            cid, text = _annotate_record(json.loads(src.read_text(encoding="utf-8")))
            (out / f"{cid}.json").write_text(text, encoding="utf-8")
            n += 1
        console.print(f"[green]wrote {n} annotated files to {out}[/]")
    else:
        raise typer.BadParameter("pass --from-file or --circulars-dir")


@app.command()
def fetch(
    since: int = typer.Option(0, "--since", help="lowest circular id to fetch"),
) -> None:
    """Fetch new GCN circulars from gcn.nasa.gov. (Sprint 5)"""
    console.print(f"[yellow]not yet implemented[/]: fetch {since=}")
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
