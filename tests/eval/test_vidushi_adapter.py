"""Tests for the Vidushi CSV adapter."""

from __future__ import annotations

from circex.data.swift_gold import SwiftEvaluationRow
from circex.eval.vidushi_adapter import (
    vidushi_gold_extraction,
    vidushi_predicted_extraction,
)


def _row(**kw: object) -> SwiftEvaluationRow:
    defaults = {
        "circular_id": 100,
        "text": "",
        "circular_date": "",
        "actual_redshift": None,
        "actual_grb_number": None,
        "actual_telescope": None,
        "actual_redshift_type": None,
        "predicted_redshift": None,
        "predicted_grb_number": None,
        "predicted_telescope": None,
        "predicted_redshift_type": None,
    }
    defaults.update(kw)
    return SwiftEvaluationRow(**defaults)  # type: ignore[arg-type]


def test_gold_extraction_event_name_normalized() -> None:
    row = _row(actual_grb_number="GRB200101A")
    ext = vidushi_gold_extraction(row)
    assert ext.event is not None
    assert ext.event.event_name == "GRB 200101A"


def test_gold_extraction_with_redshift_and_type() -> None:
    row = _row(actual_redshift=1.234, actual_redshift_type="host")
    ext = vidushi_gold_extraction(row)
    assert ext.redshift is not None
    assert ext.redshift.redshift == 1.234
    assert ext.redshift.redshift_type == "host"


def test_predicted_extraction_preserves_telescope() -> None:
    row = _row(predicted_telescope="VLT/X-shooter")
    ext = vidushi_predicted_extraction(row)
    assert ext.reporter is not None
    assert ext.reporter.instrument == "VLT/X-shooter"


def test_event_name_handles_unprefixed_id() -> None:
    row = _row(actual_grb_number="200101A")
    ext = vidushi_gold_extraction(row)
    assert ext.event is not None
    assert ext.event.event_name == "GRB 200101A"


def test_event_name_handles_messy_input() -> None:
    row = _row(actual_grb_number="grb 240617a")
    ext = vidushi_gold_extraction(row)
    assert ext.event is not None
    assert ext.event.event_name == "GRB 240617A"


def test_redshift_type_canonicalization() -> None:
    # "host galaxy" should map to "host"
    row = _row(predicted_redshift=0.1, predicted_redshift_type="host galaxy")
    ext = vidushi_predicted_extraction(row)
    assert ext.redshift is not None
    assert ext.redshift.redshift_type == "host"


def test_unknown_redshift_type_becomes_null() -> None:
    row = _row(actual_redshift=0.5, actual_redshift_type="some other")
    ext = vidushi_gold_extraction(row)
    assert ext.redshift is not None
    assert ext.redshift.redshift_type is None


def test_all_null_row_produces_extraction_with_no_fields() -> None:
    row = _row()
    ext = vidushi_gold_extraction(row)
    assert ext.event is None
    assert ext.redshift is None
    assert ext.reporter is None
