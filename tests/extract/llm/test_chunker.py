"""Tests for the chunker + deterministic merge."""

from __future__ import annotations

from circex.extract.llm.chunker import chunk_body, merge_extractions
from circex.schema import (
    CircularExtraction,
    Event,
    ExtractionMeta,
    PhotometryExt,
    Redshift,
    TimeOffset,
)


def test_short_body_returns_single_chunk() -> None:
    body = "Short circular body."
    assert chunk_body(body) == [body]


def test_short_body_under_threshold_no_split() -> None:
    body = "x" * 1000
    assert chunk_body(body) == [body]


def test_long_body_splits_into_multiple_chunks() -> None:
    paragraph = ("A" * 5000) + "\n\n"
    body = paragraph * 10  # ~50k chars
    chunks = chunk_body(body, threshold=10_000, chunk_size=10_000, overlap=500)
    assert len(chunks) > 1


def test_merge_empty_returns_minimal_extraction() -> None:
    meta = ExtractionMeta(extractor="test")
    result = merge_extractions(123, [], meta)
    assert result.circular_id == 123
    assert result.photometry == []


def test_merge_unions_photometry_rows() -> None:
    meta = ExtractionMeta(extractor="test")
    chunk_a = CircularExtraction(
        circular_id=1,
        photometry=[PhotometryExt(filter="r", mag=18.5)],
        extraction_meta=meta,
    )
    chunk_b = CircularExtraction(
        circular_id=1,
        photometry=[
            PhotometryExt(filter="r", mag=18.5),  # duplicate — deduped
            PhotometryExt(filter="g", mag=19.1),
        ],
        extraction_meta=meta,
    )
    merged = merge_extractions(1, [chunk_a, chunk_b], meta)
    assert len(merged.photometry) == 2
    mags = {p.mag for p in merged.photometry}
    assert mags == {18.5, 19.1}


def test_merge_unions_time_offsets() -> None:
    meta = ExtractionMeta(extractor="test")
    chunk_a = CircularExtraction(
        circular_id=1,
        time_offsets=[TimeOffset(value=100.0, unit="s", reference="T+")],
        extraction_meta=meta,
    )
    chunk_b = CircularExtraction(
        circular_id=1,
        time_offsets=[TimeOffset(value=200.0, unit="s", reference="T+")],
        extraction_meta=meta,
    )
    merged = merge_extractions(1, [chunk_a, chunk_b], meta)
    assert len(merged.time_offsets) == 2


def test_merge_first_non_null_wins_for_scalars() -> None:
    meta = ExtractionMeta(extractor="test")
    chunk_a = CircularExtraction(
        circular_id=1,
        event=Event(event_name="GRB 240101A"),
        extraction_meta=meta,
    )
    chunk_b = CircularExtraction(
        circular_id=1,
        event=Event(event_name="GRB 240101B"),  # ignored: chunk_a wins
        redshift=Redshift(redshift=0.5),
        extraction_meta=meta,
    )
    merged = merge_extractions(1, [chunk_a, chunk_b], meta)
    assert merged.event is not None
    assert merged.event.event_name == "GRB 240101A"
    assert merged.redshift is not None and merged.redshift.redshift == 0.5


def test_merge_invariant_single_chunk_equivalent() -> None:
    """chunk_then_merge of a short body equals single-pass."""
    meta = ExtractionMeta(extractor="test")
    original = CircularExtraction(
        circular_id=1,
        event=Event(event_name="GRB X"),
        photometry=[PhotometryExt(filter="r", mag=18.0)],
        extraction_meta=meta,
    )
    merged = merge_extractions(1, [original], meta)
    assert merged.circular_id == original.circular_id
    assert merged.event == original.event
    assert merged.photometry == original.photometry
