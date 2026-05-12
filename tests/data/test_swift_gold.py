"""Tests for circex.data.swift_gold."""

from __future__ import annotations

from pathlib import Path

from circex.data.swift_gold import load_swift_evaluation


def _write_redshift_csv(path: Path) -> None:
    path.write_text(
        "Circular Number,Text,Actual Redshift,Predicted Redshift,Actual GRB Number,"
        "Predicted GRB Number,Actual Telescope Name,Predicted Telescope Name,"
        "Actual Redshift Type,Predicted Redshift Type,Circular Date\n"
        "123,Some text,1.23,1.20,GRB 200101A,GRB200101A,VLT/X-shooter,VLT,"
        "spectroscopic,spectroscopic,2020-01-01\n"
        "124,No z,,,,,,nan,,,2020-01-02\n",
        encoding="utf-8",
    )


def test_load_swift_evaluation_parses_gold_and_pred(tmp_path: Path) -> None:
    path = tmp_path / "redshift_accuracy.csv"
    _write_redshift_csv(path)
    rows = list(load_swift_evaluation(path))
    assert len(rows) == 2
    first = rows[0]
    assert first.circular_id == 123
    assert first.actual_redshift == 1.23
    assert first.predicted_redshift == 1.20
    assert first.actual_telescope == "VLT/X-shooter"
    assert first.predicted_telescope == "VLT"
    assert first.actual_redshift_type == "spectroscopic"
    second = rows[1]
    assert second.actual_redshift is None
    assert second.predicted_telescope is None
