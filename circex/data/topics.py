"""Topic labels from Vidushi's observation-based clustering.

Source: references/circulars-nlp-paper/tables/topic-modeling-tables/
observation_based_topics.csv

Columns: Circular ID, Subject, Date, Label
Label values: "Optical Observations", "High Energy Observations", "Radio Observations",
              "Neutrinos", "Gravitational Wave"

Note: a few rows in this CSV have non-integer Circular IDs (e.g. -4.0). Those are
treated as malformed and skipped.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TOPICS_CSV = Path(
    "references/circulars-nlp-paper/tables/topic-modeling-tables/observation_based_topics.csv"
)

OPTICAL_LABEL = "Optical Observations"


@dataclass(frozen=True)
class TopicLabel:
    circular_id: int
    subject: str
    date: str
    label: str


def _coerce_circular_id(raw: str) -> int | None:
    """Parse a Circular ID cell; return None for malformed/negative/zero values."""
    try:
        as_float = float(raw)
    except ValueError:
        return None
    if as_float <= 0 or not as_float.is_integer():
        return None
    return int(as_float)


def load_topic_labels(path: Path = DEFAULT_TOPICS_CSV) -> Iterator[TopicLabel]:
    """Stream TopicLabel records from the CSV, skipping malformed rows."""
    if not path.exists():
        raise FileNotFoundError(
            f"Topics CSV not found at {path}. Clone nasa-gcn/circulars-nlp-paper into references/."
        )
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = _coerce_circular_id(row.get("Circular ID", ""))
            if cid is None:
                continue
            yield TopicLabel(
                circular_id=cid,
                subject=row.get("Subject", ""),
                date=row.get("Date", ""),
                label=row.get("Label", ""),
            )


def load_optical_ids(path: Path = DEFAULT_TOPICS_CSV) -> list[int]:
    """Return the sorted list of circular IDs labeled 'Optical Observations'."""
    return sorted(
        record.circular_id for record in load_topic_labels(path) if record.label == OPTICAL_LABEL
    )
