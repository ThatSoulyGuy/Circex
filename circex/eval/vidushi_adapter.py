"""Project Vidushi's redshift_accuracy.csv rows into CircularExtraction shapes.

The CSV has both "Actual" columns (Swift-catalog gold) and "Predicted" columns
(her Mistral-7B pipeline output). We produce two CircularExtraction per row:
one for gold, one for her predictions. Both go through the same metrics
comparator the regex/Claude/Ollama extractors are evaluated with.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from circex.data.swift_gold import (
    SwiftEvaluationRow as _SwiftRow,
)
from circex.data.swift_gold import (
    load_swift_evaluation,
)
from circex.schema import (
    CircularExtraction,
    Event,
    ExtractionMeta,
    PhotometryExt,
    Redshift,
    RedshiftMeasure,
    RedshiftType,
    Reporter,
)

# Re-export for convenience.
SwiftEvaluationRow = _SwiftRow


_REDSHIFT_TYPE_MAP: dict[str, RedshiftType] = {
    "emission": "emission",
    "absorption": "absorption",
    "host": "host",
    "host galaxy": "host",
}


def _canon_redshift_type(value: str | None) -> RedshiftType | None:
    if value is None:
        return None
    return _REDSHIFT_TYPE_MAP.get(value.strip().lower())


_REDSHIFT_MEASURE_MAP: dict[str, RedshiftMeasure] = {
    "spectroscopic": "spectroscopic",
    "photometric": "photometric",
}


def _canon_redshift_measure(value: str | None) -> RedshiftMeasure | None:
    """The CSV's "Redshift Type" column records how the redshift was measured
    (Spectroscopic / Photometric), which is our `redshift_measure`. Its
    "No Information" rows stay null."""
    if value is None:
        return None
    return _REDSHIFT_MEASURE_MAP.get(value.strip().lower())


def _grb_event_name(grb_number: str | None) -> str | None:
    if grb_number is None:
        return None
    text = grb_number.strip()
    if not text:
        return None
    # Normalize "GRB200101A", "GRB 200101A", "200101A" -> "GRB 200101A".
    match = re.match(r"^(?:GRB\s*)?(\d{6}[A-Z]?)$", text, re.IGNORECASE)
    if match:
        return f"GRB {match.group(1).upper()}"
    return text


def _row_to_extraction(
    row: SwiftEvaluationRow,
    *,
    side: Literal["gold", "predicted"],
    extractor_id: str,
) -> CircularExtraction:
    """Build a partial CircularExtraction populated from the four 4-field columns."""
    if side == "gold":
        z = row.actual_redshift
        z_measure = _canon_redshift_measure(row.actual_redshift_type)
        z_type = _canon_redshift_type(row.actual_redshift_type)
        grb = row.actual_grb_number
        telescope = row.actual_telescope
    else:
        z = row.predicted_redshift
        z_measure = _canon_redshift_measure(row.predicted_redshift_type)
        z_type = _canon_redshift_type(row.predicted_redshift_type)
        grb = row.predicted_grb_number
        telescope = row.predicted_telescope

    redshift_obj: Redshift | None = None
    if z is not None or z_type is not None or z_measure is not None:
        redshift_obj = Redshift(
            redshift=z,
            redshift_measure=z_measure,
            redshift_type=z_type,
        )

    event_name = _grb_event_name(grb)
    event_obj: Event | None = Event(event_name=event_name) if event_name else None

    # Vidushi reports "telescope name" as a string. The schema homes telescope
    # name in two places: photometry[].telescope and reporter.instrument. We
    # use a synthetic one-row photometry entry so the metrics comparator picks
    # the telescope via _first_telescope (which falls back to reporter).
    photometry: list[PhotometryExt] = []
    reporter: Reporter | None = None
    if telescope:
        reporter = Reporter(instrument=telescope)

    return CircularExtraction(
        circular_id=row.circular_id,
        event=event_obj,
        redshift=redshift_obj,
        photometry=photometry,
        reporter=reporter,
        extraction_meta=ExtractionMeta(extractor=extractor_id),
    )


def vidushi_gold_extraction(row: SwiftEvaluationRow) -> CircularExtraction:
    return _row_to_extraction(row, side="gold", extractor_id="swift-gold")


def vidushi_predicted_extraction(row: SwiftEvaluationRow) -> CircularExtraction:
    return _row_to_extraction(row, side="predicted", extractor_id="vidushi-mistral")


@dataclass(frozen=True)
class VidushiEvalSet:
    rows: list[SwiftEvaluationRow]
    gold: list[CircularExtraction]
    predicted: list[CircularExtraction]


def load_vidushi_eval(
    path: Path | None = None,
) -> VidushiEvalSet:
    """Load redshift_accuracy.csv; build paired gold + predicted CircularExtractions."""
    rows = list(load_swift_evaluation(path)) if path else list(load_swift_evaluation())
    return VidushiEvalSet(
        rows=rows,
        gold=[vidushi_gold_extraction(r) for r in rows],
        predicted=[vidushi_predicted_extraction(r) for r in rows],
    )
