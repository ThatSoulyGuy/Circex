"""Render eval results as markdown.

Headline table: rows = extractor, columns = field, cells = F1 (precision/recall
in parentheses). Plus a tokens/$$$/latency row per extractor. Failure-case
section shows the first K disagreements per field per extractor.

Beats-Vidushi delta: when the extractor list includes the 'vidushi-mistral'
adapter, a column shows F1(extractor) - F1(vidushi) on her 4 shared fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from circex.eval.metrics import (
    Comparison,
    FieldMetrics,
    compare_extractions,
    compute_field_metrics,
)
from circex.schema import CircularExtraction

# Fields Vidushi covered. Used for the headline "beats Vidushi" delta column.
VIDUSHI_FIELDS = {
    "event.event_name",  # her "GRB number"
    "redshift.redshift",
    "redshift.redshift_measure",
    "telescope_name",
}


@dataclass
class ExtractorRun:
    """One extractor's full run on a fixed gold set."""

    extractor_id: str
    extractions: list[CircularExtraction]
    total_cost_usd: float = 0.0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None


@dataclass
class ExtractorReport:
    extractor_id: str
    metrics: dict[str, FieldMetrics]
    n_circulars: int
    cost_usd: float
    tokens_in: int
    tokens_out: int
    p50_latency_ms: float | None
    p95_latency_ms: float | None
    comparisons: list[Comparison] = field(default_factory=list)


def _percentiles(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    sorted_vals = sorted(values)
    p50 = sorted_vals[len(sorted_vals) // 2]
    p95 = sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * 0.95))]
    return p50, p95


def aggregate_run_telemetry(extractions: list[CircularExtraction]) -> dict[str, float]:
    cost = 0.0
    tin = 0
    tout = 0
    latencies: list[float] = []
    for e in extractions:
        if e.extraction_meta.cost_usd is not None:
            cost += e.extraction_meta.cost_usd
        if e.extraction_meta.tokens_in is not None:
            tin += e.extraction_meta.tokens_in
        if e.extraction_meta.tokens_out is not None:
            tout += e.extraction_meta.tokens_out
        if e.extraction_meta.latency_ms is not None:
            latencies.append(e.extraction_meta.latency_ms)
    p50, p95 = _percentiles(latencies)
    return {
        "cost_usd": cost,
        "tokens_in": float(tin),
        "tokens_out": float(tout),
        "p50_latency_ms": p50 if p50 is not None else float("nan"),
        "p95_latency_ms": p95 if p95 is not None else float("nan"),
    }


def evaluate_extractor(
    extractor_id: str,
    extractions: list[CircularExtraction],
    gold: list[CircularExtraction],
) -> ExtractorReport:
    """Compare extractor outputs against gold, return per-field metrics."""
    gold_by_id = {g.circular_id: g for g in gold}
    comparisons: list[Comparison] = []
    for pred in extractions:
        gold_e = gold_by_id.get(pred.circular_id)
        if gold_e is None:
            continue
        comparisons.extend(compare_extractions(gold_e, pred))

    telemetry = aggregate_run_telemetry(extractions)
    return ExtractorReport(
        extractor_id=extractor_id,
        metrics=compute_field_metrics(comparisons),
        n_circulars=len(extractions),
        cost_usd=telemetry["cost_usd"],
        tokens_in=int(telemetry["tokens_in"]),
        tokens_out=int(telemetry["tokens_out"]),
        p50_latency_ms=None
        if telemetry["p50_latency_ms"] != telemetry["p50_latency_ms"]
        else telemetry["p50_latency_ms"],
        p95_latency_ms=None
        if telemetry["p95_latency_ms"] != telemetry["p95_latency_ms"]
        else telemetry["p95_latency_ms"],
        comparisons=comparisons,
    )


def _fmt_f1(m: FieldMetrics | None) -> str:
    if m is None or m.f1 is None:
        return "—"
    return f"{m.f1:.3f}"


def _fmt_pr(m: FieldMetrics | None) -> str:
    if m is None or m.precision is None or m.recall is None:
        return "—"
    return f"P {m.precision:.3f} / R {m.recall:.3f}"


def _fmt_support(m: FieldMetrics | None) -> str:
    if m is None:
        return "0"
    return str(m.support)


def _fmt_money(value: float) -> str:
    return f"${value:.4f}" if value > 0 else "—"


def _fmt_ms(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}"


def render_report(
    reports: list[ExtractorReport],
    fields: list[str] | None = None,
    vidushi_id: str = "vidushi-mistral",
) -> str:
    """Render a markdown report. `fields` defaults to a curated headline list."""
    fields = fields or [
        "event.event_name",
        "telescope_name",
        "redshift.redshift",
        "redshift.redshift_measure",
        "localization.ra",
        "localization.dec",
        "classification.classification",
        "photometry[row]",
        "time_offsets[row]",
    ]

    vidushi_report = next((r for r in reports if r.extractor_id == vidushi_id), None)

    lines: list[str] = []
    lines.append("# Eval v1\n")
    lines.append(f"Generated: {datetime.now(UTC).isoformat(timespec='seconds')}\n")
    lines.append(f"Extractors: {', '.join(r.extractor_id for r in reports)}\n")

    # ---- Headline F1 table ----
    lines.append("\n## Per-field F1\n")
    header = "| Extractor | " + " | ".join(fields) + " |"
    sep = "|---" * (len(fields) + 1) + "|"
    lines.append(header)
    lines.append(sep)
    for r in reports:
        cells = [r.extractor_id]
        for f in fields:
            cells.append(_fmt_f1(r.metrics.get(f)))
        lines.append("| " + " | ".join(cells) + " |")

    # ---- Precision / recall ----
    lines.append("\n## Per-field Precision / Recall\n")
    lines.append(header)
    lines.append(sep)
    for r in reports:
        cells = [r.extractor_id]
        for f in fields:
            cells.append(_fmt_pr(r.metrics.get(f)))
        lines.append("| " + " | ".join(cells) + " |")

    # ---- Support (non-null gold) ----
    lines.append("\n## Gold support per field (TP + FN)\n")
    lines.append(header)
    lines.append(sep)
    # Support is gold-only; pick any extractor's metrics for the support count
    # (they should agree). Use the first report.
    first = reports[0]
    support_cells = " | ".join(_fmt_support(first.metrics.get(f)) for f in fields)
    lines.append(f"| (gold) | {support_cells} |")

    # ---- Beats-Vidushi delta on her 4 fields ----
    if vidushi_report is not None:
        lines.append("\n## Δ F1 vs Vidushi (her 4 fields)\n")
        vidushi_fields = [f for f in fields if f in VIDUSHI_FIELDS]
        header_v = "| Extractor | " + " | ".join(vidushi_fields) + " |"
        sep_v = "|---" * (len(vidushi_fields) + 1) + "|"
        lines.append(header_v)
        lines.append(sep_v)
        for r in reports:
            if r.extractor_id == vidushi_id:
                continue
            cells = [r.extractor_id]
            for f in vidushi_fields:
                m_r = r.metrics.get(f)
                m_v = vidushi_report.metrics.get(f)
                if m_r is None or m_r.f1 is None or m_v is None or m_v.f1 is None:
                    cells.append("—")
                else:
                    delta = m_r.f1 - m_v.f1
                    sign = "+" if delta >= 0 else ""
                    cells.append(f"{sign}{delta:.3f}")
            lines.append("| " + " | ".join(cells) + " |")

    # ---- Cost / latency ----
    lines.append("\n## Cost & latency\n")
    lines.append("| Extractor | n | $/run | tokens in | tokens out | p50 ms | p95 ms |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in reports:
        row = (
            f"| {r.extractor_id} | {r.n_circulars} | {_fmt_money(r.cost_usd)} "
            f"| {r.tokens_in} | {r.tokens_out} "
            f"| {_fmt_ms(r.p50_latency_ms)} | {_fmt_ms(r.p95_latency_ms)} |"
        )
        lines.append(row)

    # ---- Failure-case browser ----
    lines.append("\n## Failure-case browser\n")
    lines.append("First 3 disagreements per (extractor, field).\n")
    for r in reports:
        if r.extractor_id == vidushi_id:
            continue
        lines.append(f"### {r.extractor_id}\n")
        for f in fields:
            m = r.metrics.get(f)
            if m is None or not m.failures:
                continue
            lines.append(f"**{f}** ({m.tp} TP / {m.fp} FP / {m.fn} FN)\n")
            for c in m.failures[:3]:
                lines.append(
                    f"- circular {c.circular_id} — {c.outcome}: "
                    f"gold={_truncate(c.gold)} pred={_truncate(c.pred)}"
                )
            lines.append("")

    return "\n".join(lines) + "\n"


def _truncate(value: object, max_len: int = 80) -> str:
    if value is None:
        return "null"
    text = json.dumps(value, default=str)
    return text if len(text) <= max_len else text[:max_len] + "…"


def write_report(reports: list[ExtractorReport], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_report(reports), encoding="utf-8")
