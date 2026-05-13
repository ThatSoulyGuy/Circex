"""Vidushi's redshift evaluation CSV: Swift-derived gold + her Mistral-7B predictions.

Source: references/circulars-nlp-paper/tables/information-extraction-tables/
eval_with_SWIFT/redshift_accuracy.csv (13,593 rows)

Columns:
    Circular Number, Text,
    Actual Redshift, Predicted Redshift,
    Actual GRB Number, Predicted GRB Number,
    Actual Telescope Name, Predicted Telescope Name,
    Actual Redshift Type, Predicted Redshift Type,
    Circular Date

The 'Actual' columns are Swift-catalog gold (`data/swift_redshift_data.csv`).
The 'Predicted' columns are Vidushi's pipeline outputs — Circex must beat these
on F1 per the PDF acceptance criterion.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REDSHIFT_CSV = Path(
    "references/circulars-nlp-paper/tables/information-extraction-tables/"
    "eval_with_SWIFT/redshift_accuracy.csv"
)


@dataclass(frozen=True)
class SwiftEvaluationRow:
    circular_id: int
    text: str
    circular_date: str

    # Gold (Swift catalog)
    actual_redshift: float | None
    actual_grb_number: str | None
    actual_telescope: str | None
    actual_redshift_type: str | None

    # Vidushi's Mistral-7B predictions
    predicted_redshift: float | None
    predicted_grb_number: str | None
    predicted_telescope: str | None
    predicted_redshift_type: str | None


def _to_float(s: str) -> float | None:
    s = (s or "").strip()
    if not s or s.lower() in _NULL_SENTINELS:
        return None
    try:
        return float(s)
    except ValueError:
        return None


_NULL_SENTINELS: frozenset[str] = frozenset({
    "nan", "none", "null", "no information", "n/a", "na", "-",
})


def _to_str(s: str) -> str | None:
    s = (s or "").strip()
    return s if s and s.lower() not in _NULL_SENTINELS else None


def load_swift_evaluation(path: Path = DEFAULT_REDSHIFT_CSV) -> Iterator[SwiftEvaluationRow]:
    """Stream SwiftEvaluationRow records from the redshift_accuracy.csv."""
    if not path.exists():
        raise FileNotFoundError(
            f"redshift_accuracy.csv not found at {path}. Clone "
            f"nasa-gcn/circulars-nlp-paper into references/."
        )
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                cid = int(float(row["Circular Number"]))
            except (ValueError, KeyError):
                continue
            yield SwiftEvaluationRow(
                circular_id=cid,
                text=row.get("Text", ""),
                circular_date=row.get("Circular Date", ""),
                actual_redshift=_to_float(row.get("Actual Redshift", "")),
                actual_grb_number=_to_str(row.get("Actual GRB Number", "")),
                actual_telescope=_to_str(row.get("Actual Telescope Name", "")),
                actual_redshift_type=_to_str(row.get("Actual Redshift Type", "")),
                predicted_redshift=_to_float(row.get("Predicted Redshift", "")),
                predicted_grb_number=_to_str(row.get("Predicted GRB Number", "")),
                predicted_telescope=_to_str(row.get("Predicted Telescope Name", "")),
                predicted_redshift_type=_to_str(row.get("Predicted Redshift Type", "")),
            )
