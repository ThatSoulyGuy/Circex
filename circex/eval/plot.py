"""F1 visualization for the eval harness.

Two charts in one figure:
  1. Grouped-bar: F1 per field across extractors (apples-to-apples).
  2. Δ-vs-baseline: horizontal bar of F1(extractor) - F1(baseline) per field,
     showing exactly where each LLM extractor beats (or loses to) the regex
     baseline.

matplotlib is an optional dependency. Install with `pip install -e ".[plot]"`
or `pip install matplotlib`. The function raises a clear error otherwise.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from circex.eval.report import ExtractorReport

if TYPE_CHECKING:
    pass

DEFAULT_FIELDS = [
    "event.event_name",
    "telescope_name",
    "redshift.redshift",
    "redshift.redshift_type",
    "localization.ra",
    "localization.dec",
    "classification.classification",
    "photometry[row]",
    "time_offsets[row]",
]


def _require_matplotlib() -> object:
    try:
        import matplotlib
    except ImportError as exc:
        raise ImportError(
            "matplotlib is required for `circex eval --plot`. Install with: pip install matplotlib"
        ) from exc
    matplotlib.use("Agg")  # non-interactive backend; safe on CI/headless
    return matplotlib


def _f1_or_none(report: ExtractorReport, field: str) -> float | None:
    m = report.metrics.get(field)
    if m is None:
        return None
    return m.f1


def _fields_with_data(reports: list[ExtractorReport], candidate_fields: list[str]) -> list[str]:
    """Drop fields where every extractor reports None F1 (no gold support)."""
    keep: list[str] = []
    for f in candidate_fields:
        if any(_f1_or_none(r, f) is not None for r in reports):
            keep.append(f)
    return keep


def plot_eval(
    reports: list[ExtractorReport],
    out_path: Path,
    fields: list[str] | None = None,
    baseline_id: str = "regex-v1",
    title_suffix: str | None = None,
) -> Path:
    """Render a 2-panel figure: grouped-bar F1 + Δ-vs-baseline.

    `baseline_id` is the extractor we measure others against in the second
    panel. Defaults to regex-v1; pass e.g. 'vidushi-mistral' to compare against
    her baseline instead.

    Returns the output path.
    """
    _require_matplotlib()
    import matplotlib.pyplot as plt
    import numpy as np

    fields = _fields_with_data(reports, fields or DEFAULT_FIELDS)
    if not fields:
        raise ValueError("no fields have any F1 data — nothing to plot")

    n_extractors = len(reports)
    n_fields = len(fields)

    # ── Top panel: grouped F1 bars ─────────────────────────────────────────
    fig, (ax_top, ax_bot) = plt.subplots(
        2,
        1,
        figsize=(max(10, n_fields * 1.2), 9),
        gridspec_kw={"height_ratios": [3, 2], "hspace": 0.45},
        constrained_layout=True,
    )

    bar_width = 0.8 / n_extractors
    x = np.arange(n_fields)

    # Use a color-blind safe palette (Wong 2011).
    palette = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442"]

    NO_DATA_HEIGHT = 0.03  # short hatched bar for "no gold support"
    for i, report in enumerate(reports):
        scores = [_f1_or_none(report, f) for f in fields]
        heights = [s if s is not None else NO_DATA_HEIGHT for s in scores]
        color = palette[i % len(palette)]
        bars = ax_top.bar(
            x + i * bar_width,
            heights,
            bar_width,
            label=report.extractor_id,
            color=color,
            edgecolor="black",
            linewidth=0.5,
        )
        for bar, score in zip(bars, scores, strict=False):
            if score is None:
                bar.set_hatch("///")
                bar.set_alpha(0.25)
                ax_top.text(
                    bar.get_x() + bar.get_width() / 2,
                    NO_DATA_HEIGHT + 0.015,
                    "n/a",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    color="gray",
                )
                continue
            ax_top.text(
                bar.get_x() + bar.get_width() / 2,
                score + 0.015,
                f"{score:.2f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    ax_top.set_xticks(x + bar_width * (n_extractors - 1) / 2)
    ax_top.set_xticklabels(fields, rotation=30, ha="right", fontsize=9)
    ax_top.set_ylim(0, 1.05)
    ax_top.set_ylabel("F1 score", fontsize=11)
    title = "Per-field F1 comparison"
    if title_suffix:
        title += f" — {title_suffix}"
    ax_top.set_title(title, fontsize=12, pad=10)
    ax_top.legend(loc="lower right", fontsize=9, framealpha=0.9)
    ax_top.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.6)
    ax_top.set_axisbelow(True)

    # ── Bottom panel: Δ vs baseline ────────────────────────────────────────
    baseline_report = next((r for r in reports if r.extractor_id == baseline_id), None)
    if baseline_report is None:
        ax_bot.text(
            0.5,
            0.5,
            f"(no Δ panel — baseline {baseline_id!r} not in results)",
            ha="center",
            va="center",
            transform=ax_bot.transAxes,
            fontsize=10,
            color="gray",
        )
        ax_bot.set_axis_off()
    else:
        others = [r for r in reports if r.extractor_id != baseline_id]
        if not others:
            ax_bot.text(
                0.5,
                0.5,
                "(no Δ panel — only baseline run)",
                ha="center",
                va="center",
                transform=ax_bot.transAxes,
                fontsize=10,
                color="gray",
            )
            ax_bot.set_axis_off()
        else:
            width = 0.8 / len(others)
            for i, report in enumerate(others):
                deltas: list[float] = []
                for f in fields:
                    f_other = _f1_or_none(report, f)
                    f_base = _f1_or_none(baseline_report, f)
                    if f_other is None or f_base is None:
                        deltas.append(0.0)
                    else:
                        deltas.append(f_other - f_base)
                color = palette[(reports.index(report)) % len(palette)]
                bars = ax_bot.bar(
                    x + i * width,
                    deltas,
                    width,
                    label=f"{report.extractor_id} − {baseline_id}",
                    color=color,
                    edgecolor="black",
                    linewidth=0.5,
                )
                for bar, delta in zip(bars, deltas, strict=False):
                    if delta == 0:
                        continue
                    sign = "+" if delta > 0 else ""
                    y_text = delta + (0.015 if delta > 0 else -0.025)
                    va = "bottom" if delta > 0 else "top"
                    ax_bot.text(
                        bar.get_x() + bar.get_width() / 2,
                        y_text,
                        f"{sign}{delta:.2f}",
                        ha="center",
                        va=va,
                        fontsize=8,
                    )

            ax_bot.axhline(0, color="black", linewidth=0.8)
            ax_bot.set_xticks(x + width * (len(others) - 1) / 2)
            ax_bot.set_xticklabels(fields, rotation=30, ha="right", fontsize=9)
            ax_bot.set_ylabel(f"Δ F1 vs {baseline_id}", fontsize=11)
            ax_bot.set_title(f"How much better than {baseline_id}?", fontsize=12, pad=10)
            ax_bot.legend(loc="upper right", fontsize=9, framealpha=0.9)
            ax_bot.grid(axis="y", linestyle=":", linewidth=0.5, alpha=0.6)
            ax_bot.set_axisbelow(True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return out_path
