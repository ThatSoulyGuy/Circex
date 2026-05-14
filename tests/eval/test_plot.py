"""Smoke test for the plot module — verifies a PNG is produced."""

from __future__ import annotations

from pathlib import Path

import pytest

from circex.eval.plot import plot_eval
from circex.eval.report import evaluate_extractor
from circex.schema import CircularExtraction


def _ext(circular_id: int, redshift: float | None = None) -> CircularExtraction:
    payload: dict[str, object] = {
        "circular_id": circular_id,
        "extraction_meta": {"extractor": "test"},
    }
    if redshift is not None:
        payload["redshift"] = {"redshift": redshift}
    return CircularExtraction.model_validate(payload)


@pytest.fixture
def two_reports() -> list:
    gold = [_ext(1, 0.5), _ext(2, 1.0), _ext(3, 0.95)]
    perfect = [_ext(1, 0.5), _ext(2, 1.0), _ext(3, 0.95)]
    half = [_ext(1, 0.5), _ext(2, 99.0), _ext(3, 0.95)]
    return [
        evaluate_extractor("regex-v1", half, gold),
        evaluate_extractor("claude-haiku", perfect, gold),
    ]


def test_plot_writes_png(tmp_path: Path, two_reports: list) -> None:
    out = tmp_path / "eval.png"
    result = plot_eval(two_reports, out, baseline_id="regex-v1")
    assert result == out
    assert out.exists()
    # PNG signature: \x89PNG
    assert out.read_bytes()[:4] == b"\x89PNG"


def test_plot_handles_missing_baseline(tmp_path: Path, two_reports: list) -> None:
    """If the named baseline isn't in the report list, the Δ panel renders a note."""
    out = tmp_path / "eval.png"
    plot_eval(two_reports, out, baseline_id="some-nonexistent")
    assert out.exists()


def test_plot_raises_when_no_data(tmp_path: Path) -> None:
    gold = [_ext(1)]
    pred = [_ext(1)]
    reports = [evaluate_extractor("a", pred, gold)]
    out = tmp_path / "eval.png"
    with pytest.raises(ValueError, match="no fields"):
        plot_eval(reports, out)
