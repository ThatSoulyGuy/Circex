"""Per-field comparator + aggregator producing P/R/F1.

Null-handling convention (consistent across the four-way eval):
  gold null,    pred null         -> True Negative (NOT counted in TP/FP/FN)
  gold null,    pred not null     -> False Positive (extractor hallucinated)
  gold not null, pred null        -> False Negative (extractor missed)
  gold not null, pred not null,
                values match      -> True Positive
                values mismatch   -> 1 FP + 1 FN (both wrong)

Field comparison rules:
  - Numeric (redshift, ra, dec, mag): abs-diff within tolerance per FIELD_TOLERANCES.
  - String (telescope, event_name, GRB number): normalized string equality
    (strip whitespace, casefold, collapse multiple spaces).
  - Enum (mag_system, redshift_measure, redshift_type): exact equality.
  - List (photometry, time_offsets): greedy row matching by (filter, mag)
    or (value, unit). Each matched pair counts at the row level; unmatched
    rows are FP (pred) or FN (gold).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from circex.schema import CircularExtraction, PhotometryExt, TimeOffset

# Per-field numeric tolerance (absolute difference). Tweakable; consistent
# with the labeling spec.
FIELD_TOLERANCES: dict[str, float] = {
    "redshift": 0.001,
    "localization.ra": 0.001,
    "localization.dec": 0.001,
    "photometry.mag": 0.05,
    "photometry.limiting_mag": 0.2,
    "photometry.mag_error": 0.05,
}


# ---------- helpers ----------

_WS_RE = re.compile(r"\s+")


def _normalize_str(value: object) -> str:
    """Casefold + whitespace collapse for soft string equality."""
    if not isinstance(value, str):
        return str(value)
    return _WS_RE.sub(" ", value).strip().casefold()


def _str_eq(a: object, b: object) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return _normalize_str(a) == _normalize_str(b)


def _num_close(a: object, b: object, tol: float) -> bool:
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return False
    return abs(float(a) - float(b)) <= tol


def _is_null(value: Any) -> bool:
    return value is None


def _event_name_set(value: Any) -> set[str]:
    """Event names can be str or list[str]; return a normalized set."""
    if value is None:
        return set()
    if isinstance(value, list):
        return {_normalize_str(v) for v in value if v}
    return {_normalize_str(value)}


# ---------- field comparisons ----------


@dataclass(frozen=True)
class Comparison:
    field_path: str
    circular_id: int
    outcome: Literal["TP", "FP", "FN", "TN", "MM"]
    gold: Any = None
    pred: Any = None


def _compare_scalar(
    field_path: str,
    circular_id: int,
    gold: Any,
    pred: Any,
    matcher: Any,
) -> Comparison:
    """Generic null-aware scalar comparator.

    Outcomes:
      both null         -> TN
      gold null only    -> FP (hallucination)
      pred null only    -> FN (missed)
      both set, match   -> TP
      both set, differ  -> MM (counted as 1 FP + 1 FN in aggregation)
    """
    g_null = _is_null(gold)
    p_null = _is_null(pred)
    outcome: Literal["TP", "FP", "FN", "TN", "MM"]
    if g_null and p_null:
        outcome = "TN"
    elif g_null and not p_null:
        outcome = "FP"
    elif not g_null and p_null:
        outcome = "FN"
    elif matcher(gold, pred):
        outcome = "TP"
    else:
        outcome = "MM"
    return Comparison(
        field_path=field_path, circular_id=circular_id, outcome=outcome, gold=gold, pred=pred
    )


def _compare_event_name(
    circular_id: int, gold: Any, pred: Any
) -> Comparison:
    """Event names: list/string-tolerant; match if intersection non-empty."""
    g_set = _event_name_set(gold)
    p_set = _event_name_set(pred)
    outcome: Literal["TP", "FP", "FN", "TN", "MM"]
    if not g_set and not p_set:
        outcome = "TN"
    elif not g_set and p_set:
        outcome = "FP"
    elif g_set and not p_set:
        outcome = "FN"
    elif g_set & p_set:
        outcome = "TP"
    else:
        outcome = "MM"
    return Comparison(
        field_path="event.event_name",
        circular_id=circular_id,
        outcome=outcome,
        gold=gold,
        pred=pred,
    )


# ---------- list comparators ----------


def _photometry_row_key(p: PhotometryExt) -> tuple[str | None, float | None]:
    """Greedy match key: (filter, mag-or-limit)."""
    return (p.filter, p.mag if p.mag is not None else p.limiting_mag)


def _photometry_row_match(g: PhotometryExt, p: PhotometryExt) -> bool:
    if g.filter != p.filter:
        return False
    # Match either detection mag or upper limit, within tolerance.
    if g.mag is not None and p.mag is not None:
        return abs(g.mag - p.mag) <= FIELD_TOLERANCES["photometry.mag"]
    if g.limiting_mag is not None and p.limiting_mag is not None:
        return abs(g.limiting_mag - p.limiting_mag) <= FIELD_TOLERANCES["photometry.limiting_mag"]
    return False


def _compare_photometry(
    circular_id: int, gold: list[PhotometryExt], pred: list[PhotometryExt]
) -> list[Comparison]:
    """Greedy row matching; each row pair generates one TP/FP/FN."""
    results: list[Comparison] = []
    matched_pred: set[int] = set()

    for g in gold:
        match_idx: int | None = None
        for i, p in enumerate(pred):
            if i in matched_pred:
                continue
            if _photometry_row_match(g, p):
                match_idx = i
                break
        if match_idx is not None:
            matched_pred.add(match_idx)
            results.append(
                Comparison(
                    field_path="photometry[row]",
                    circular_id=circular_id,
                    outcome="TP",
                    gold=g.model_dump(exclude_none=True),
                    pred=pred[match_idx].model_dump(exclude_none=True),
                )
            )
        else:
            results.append(
                Comparison(
                    field_path="photometry[row]",
                    circular_id=circular_id,
                    outcome="FN",
                    gold=g.model_dump(exclude_none=True),
                )
            )

    for i, p in enumerate(pred):
        if i not in matched_pred:
            results.append(
                Comparison(
                    field_path="photometry[row]",
                    circular_id=circular_id,
                    outcome="FP",
                    pred=p.model_dump(exclude_none=True),
                )
            )

    return results


def _compare_time_offsets(
    circular_id: int, gold: list[TimeOffset], pred: list[TimeOffset]
) -> list[Comparison]:
    """Match by (unit, abs(value)) within unit-aware tolerance."""
    matched_pred: set[int] = set()
    results: list[Comparison] = []

    for g in gold:
        match_idx: int | None = None
        for i, p in enumerate(pred):
            if i in matched_pred:
                continue
            if g.unit == p.unit and abs(g.value - p.value) <= 0.5:
                match_idx = i
                break
        if match_idx is not None:
            matched_pred.add(match_idx)
            results.append(
                Comparison(
                    field_path="time_offsets[row]",
                    circular_id=circular_id,
                    outcome="TP",
                    gold=g.model_dump(),
                    pred=pred[match_idx].model_dump(),
                )
            )
        else:
            results.append(
                Comparison(
                    field_path="time_offsets[row]",
                    circular_id=circular_id,
                    outcome="FN",
                    gold=g.model_dump(),
                )
            )

    for i, p in enumerate(pred):
        if i not in matched_pred:
            results.append(
                Comparison(
                    field_path="time_offsets[row]",
                    circular_id=circular_id,
                    outcome="FP",
                    pred=p.model_dump(),
                )
            )

    return results


# ---------- top-level extraction comparison ----------


def compare_extractions(
    gold: CircularExtraction, pred: CircularExtraction
) -> list[Comparison]:
    """Compare every field of two CircularExtractions. Returns flat list of Comparison."""
    cid = gold.circular_id
    out: list[Comparison] = []

    # event.event_name
    g_event = gold.event.event_name if gold.event else None
    p_event = pred.event.event_name if pred.event else None
    out.append(_compare_event_name(cid, g_event, p_event))

    # redshift fields
    g_red = gold.redshift
    p_red = pred.redshift
    out.append(
        _compare_scalar(
            "redshift.redshift",
            cid,
            g_red.redshift if g_red else None,
            p_red.redshift if p_red else None,
            lambda a, b: _num_close(a, b, FIELD_TOLERANCES["redshift"]),
        )
    )
    out.append(
        _compare_scalar(
            "redshift.redshift_measure",
            cid,
            g_red.redshift_measure if g_red else None,
            p_red.redshift_measure if p_red else None,
            lambda a, b: a == b,
        )
    )
    out.append(
        _compare_scalar(
            "redshift.redshift_type",
            cid,
            g_red.redshift_type if g_red else None,
            p_red.redshift_type if p_red else None,
            lambda a, b: a == b,
        )
    )

    # localization
    g_loc = gold.localization
    p_loc = pred.localization
    out.append(
        _compare_scalar(
            "localization.ra",
            cid,
            g_loc.ra if g_loc else None,
            p_loc.ra if p_loc else None,
            lambda a, b: _num_close(a, b, FIELD_TOLERANCES["localization.ra"]),
        )
    )
    out.append(
        _compare_scalar(
            "localization.dec",
            cid,
            g_loc.dec if g_loc else None,
            p_loc.dec if p_loc else None,
            lambda a, b: _num_close(a, b, FIELD_TOLERANCES["localization.dec"]),
        )
    )

    # classification (single canonical class)
    g_cls = gold.classification.classification if gold.classification else None
    p_cls = pred.classification.classification if pred.classification else None
    out.append(
        _compare_scalar(
            "classification.classification",
            cid,
            g_cls,
            p_cls,
            lambda a, b: a == b,
        )
    )

    # reporter.instrument and photometry[].telescope are both telescope-name
    # comparisons. For Vidushi parity, expose telescope_name as a derived field.
    g_telescope = _first_telescope(gold)
    p_telescope = _first_telescope(pred)
    out.append(
        _compare_scalar(
            "telescope_name",
            cid,
            g_telescope,
            p_telescope,
            _str_eq,
        )
    )

    # photometry list (row-level set semantics)
    out.extend(_compare_photometry(cid, gold.photometry, pred.photometry))
    # time_offsets list
    out.extend(_compare_time_offsets(cid, gold.time_offsets, pred.time_offsets))

    return out


def _first_telescope(extraction: CircularExtraction) -> str | None:
    """Derive a single telescope name: first photometry.telescope, else reporter.instrument."""
    for p in extraction.photometry:
        if p.telescope:
            return p.telescope
    if extraction.reporter and extraction.reporter.instrument:
        return extraction.reporter.instrument
    return None


# ---------- aggregation ----------


@dataclass
class FieldMetrics:
    field_path: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    failures: list[Comparison] = field(default_factory=list)

    @property
    def precision(self) -> float | None:
        denom = self.tp + self.fp
        return None if denom == 0 else self.tp / denom

    @property
    def recall(self) -> float | None:
        denom = self.tp + self.fn
        return None if denom == 0 else self.tp / denom

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or (p + r) == 0:
            return None
        return 2 * p * r / (p + r)

    @property
    def support(self) -> int:
        """Number of non-null gold occurrences (TP + FN)."""
        return self.tp + self.fn


def compute_field_metrics(
    comparisons: Iterable[Comparison],
    max_failures_per_field: int = 5,
) -> dict[str, FieldMetrics]:
    """Aggregate per-field metrics from a flat list of comparisons."""
    out: dict[str, FieldMetrics] = {}
    for c in comparisons:
        m = out.setdefault(c.field_path, FieldMetrics(field_path=c.field_path))
        if c.outcome == "TP":
            m.tp += 1
        elif c.outcome == "FP":
            m.fp += 1
            if len(m.failures) < max_failures_per_field:
                m.failures.append(c)
        elif c.outcome == "FN":
            m.fn += 1
            if len(m.failures) < max_failures_per_field:
                m.failures.append(c)
        elif c.outcome == "MM":
            m.fp += 1
            m.fn += 1
            if len(m.failures) < max_failures_per_field:
                m.failures.append(c)
        else:
            m.tn += 1
    return out
