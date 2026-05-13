"""Tests for the per-field comparator + aggregator."""

from __future__ import annotations

from circex.eval.metrics import (
    compare_extractions,
    compute_field_metrics,
)
from circex.schema import (
    CircularExtraction,
    Event,
    ExtractionMeta,
    Localization,
    PhotometryExt,
    Redshift,
    TimeOffset,
)


def _ext(**kwargs: object) -> CircularExtraction:
    return CircularExtraction.model_validate(
        {
            "circular_id": kwargs.pop("circular_id", 1),
            "extraction_meta": {"extractor": "test"},
            **kwargs,
        }
    )


# ---- null-handling ----


def test_both_null_is_TN() -> None:
    gold = _ext()
    pred = _ext()
    comps = compare_extractions(gold, pred)
    for c in comps:
        if c.field_path == "redshift.redshift":
            assert c.outcome == "TN"


def test_gold_null_pred_set_is_FP() -> None:
    gold = _ext()
    pred = _ext(redshift={"redshift": 0.5})
    comps = compare_extractions(gold, pred)
    z = next(c for c in comps if c.field_path == "redshift.redshift")
    assert z.outcome == "FP"


def test_gold_set_pred_null_is_FN() -> None:
    gold = _ext(redshift={"redshift": 0.5})
    pred = _ext()
    comps = compare_extractions(gold, pred)
    z = next(c for c in comps if c.field_path == "redshift.redshift")
    assert z.outcome == "FN"


def test_matching_value_is_TP() -> None:
    gold = _ext(redshift={"redshift": 0.5})
    pred = _ext(redshift={"redshift": 0.5})
    comps = compare_extractions(gold, pred)
    z = next(c for c in comps if c.field_path == "redshift.redshift")
    assert z.outcome == "TP"


def test_mismatch_is_MM() -> None:
    """A value mismatch counts as both FP (hallucination) and FN (missed)."""
    gold = _ext(redshift={"redshift": 0.5})
    pred = _ext(redshift={"redshift": 0.7})
    comps = compare_extractions(gold, pred)
    z = next(c for c in comps if c.field_path == "redshift.redshift")
    assert z.outcome == "MM"


# ---- numeric tolerance ----


def test_redshift_within_tolerance_matches() -> None:
    gold = _ext(redshift={"redshift": 1.234})
    pred = _ext(redshift={"redshift": 1.2345})  # within 0.001 tol
    z = next(c for c in compare_extractions(gold, pred) if c.field_path == "redshift.redshift")
    assert z.outcome == "TP"


def test_redshift_outside_tolerance_mismatches() -> None:
    gold = _ext(redshift={"redshift": 1.0})
    pred = _ext(redshift={"redshift": 1.5})
    z = next(c for c in compare_extractions(gold, pred) if c.field_path == "redshift.redshift")
    assert z.outcome == "MM"


def test_ra_dec_within_tolerance() -> None:
    gold = _ext(localization={"ra": 191.5320, "dec": -23.7534})
    pred = _ext(localization={"ra": 191.5325, "dec": -23.7533})  # within 0.001 tol
    comps = compare_extractions(gold, pred)
    ra = next(c for c in comps if c.field_path == "localization.ra")
    dec = next(c for c in comps if c.field_path == "localization.dec")
    assert ra.outcome == "TP"
    assert dec.outcome == "TP"


# ---- event_name with list/string mix ----


def test_event_name_string_vs_list_intersection_matches() -> None:
    gold = _ext(event={"event_name": "GRB 170817A"})
    pred = _ext(event={"event_name": ["GRB 170817A", "GW170817"]})
    e = next(c for c in compare_extractions(gold, pred) if c.field_path == "event.event_name")
    assert e.outcome == "TP"


def test_event_name_disjoint_lists_mismatch() -> None:
    gold = _ext(event={"event_name": "GRB 170817A"})
    pred = _ext(event={"event_name": "GRB 240101A"})
    e = next(c for c in compare_extractions(gold, pred) if c.field_path == "event.event_name")
    assert e.outcome == "MM"


# ---- enums ----


def test_redshift_type_enum_match() -> None:
    gold = _ext(redshift={"redshift": 0.1, "redshift_type": "host"})
    pred = _ext(redshift={"redshift": 0.1, "redshift_type": "host"})
    t = next(
        c for c in compare_extractions(gold, pred) if c.field_path == "redshift.redshift_type"
    )
    assert t.outcome == "TP"


def test_redshift_type_enum_mismatch() -> None:
    gold = _ext(redshift={"redshift": 0.1, "redshift_type": "host"})
    pred = _ext(redshift={"redshift": 0.1, "redshift_type": "emission"})
    t = next(
        c for c in compare_extractions(gold, pred) if c.field_path == "redshift.redshift_type"
    )
    assert t.outcome == "MM"


# ---- photometry list (set semantics) ----


def test_photometry_perfect_match_all_tp() -> None:
    gold = _ext(photometry=[{"filter": "r", "mag": 18.5}, {"filter": "g", "mag": 19.1}])
    pred = _ext(photometry=[{"filter": "r", "mag": 18.5}, {"filter": "g", "mag": 19.1}])
    comps = [c for c in compare_extractions(gold, pred) if c.field_path == "photometry[row]"]
    assert sum(1 for c in comps if c.outcome == "TP") == 2
    assert sum(1 for c in comps if c.outcome == "FP") == 0
    assert sum(1 for c in comps if c.outcome == "FN") == 0


def test_photometry_extra_pred_row_is_FP() -> None:
    gold = _ext(photometry=[{"filter": "r", "mag": 18.5}])
    pred = _ext(photometry=[{"filter": "r", "mag": 18.5}, {"filter": "g", "mag": 19.1}])
    comps = [c for c in compare_extractions(gold, pred) if c.field_path == "photometry[row]"]
    assert sum(1 for c in comps if c.outcome == "TP") == 1
    assert sum(1 for c in comps if c.outcome == "FP") == 1
    assert sum(1 for c in comps if c.outcome == "FN") == 0


def test_photometry_missing_pred_row_is_FN() -> None:
    gold = _ext(photometry=[{"filter": "r", "mag": 18.5}, {"filter": "g", "mag": 19.1}])
    pred = _ext(photometry=[{"filter": "r", "mag": 18.5}])
    comps = [c for c in compare_extractions(gold, pred) if c.field_path == "photometry[row]"]
    assert sum(1 for c in comps if c.outcome == "TP") == 1
    assert sum(1 for c in comps if c.outcome == "FN") == 1


def test_photometry_mag_outside_tolerance_doesnt_match() -> None:
    gold = _ext(photometry=[{"filter": "r", "mag": 18.5}])
    pred = _ext(photometry=[{"filter": "r", "mag": 20.0}])
    comps = [c for c in compare_extractions(gold, pred) if c.field_path == "photometry[row]"]
    # No match: gold becomes FN, pred becomes FP.
    assert sum(1 for c in comps if c.outcome == "FN") == 1
    assert sum(1 for c in comps if c.outcome == "FP") == 1


# ---- time_offsets list ----


def test_time_offsets_match_by_unit_and_value() -> None:
    gold = _ext(time_offsets=[{"value": 234.0, "unit": "s", "reference": "T+"}])
    pred = _ext(time_offsets=[{"value": 234.0, "unit": "s", "reference": "T+"}])
    comps = [c for c in compare_extractions(gold, pred) if c.field_path == "time_offsets[row]"]
    assert sum(1 for c in comps if c.outcome == "TP") == 1


# ---- aggregator ----


def test_compute_field_metrics_basic() -> None:
    gold = _ext(redshift={"redshift": 0.5})
    pred_good = _ext(redshift={"redshift": 0.5})
    pred_bad = _ext(redshift={"redshift": 0.6})  # MM -> +1 FP, +1 FN
    pred_null = _ext()  # FN

    comps = (
        compare_extractions(gold, pred_good)
        + compare_extractions(gold, pred_bad)
        + compare_extractions(gold, pred_null)
    )
    metrics = compute_field_metrics(comps)
    m = metrics["redshift.redshift"]
    assert m.tp == 1
    assert m.fp == 1
    assert m.fn == 2
    # precision = 1/2 = 0.5; recall = 1/3 = 0.333...; F1 ≈ 0.4
    assert m.precision == 0.5
    assert m.recall is not None
    assert abs(m.recall - 1 / 3) < 1e-9
    assert m.f1 is not None
    assert abs(m.f1 - 0.4) < 1e-9


def test_compute_field_metrics_perfect_run() -> None:
    g = _ext(redshift={"redshift": 0.5})
    p = _ext(redshift={"redshift": 0.5})
    metrics = compute_field_metrics(compare_extractions(g, p))
    m = metrics["redshift.redshift"]
    assert m.f1 == 1.0


# ---- helpers used implicitly ----


def test_imports_resolve() -> None:
    # Ensure the imports at the top still work after refactors.
    assert Event and ExtractionMeta and Localization and PhotometryExt
    assert Redshift and TimeOffset
