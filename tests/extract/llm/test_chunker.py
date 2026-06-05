"""Tests for the chunker + deterministic merge."""

from __future__ import annotations

from circex.extract.llm.chunker import chunk_body, merge_extractions
from circex.schema import (
    CircularExtraction,
    Event,
    ExtractionMeta,
    PhotometryExt,
    Redshift,
    Span,
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


# ---- notes + provenance carry-forward through merge (P2 #11, P1 #7) ----


def test_merge_carries_notes_from_chunks() -> None:
    """Per-chunk extraction_meta.notes flow into the merged extraction."""
    run_meta = ExtractionMeta(extractor="test")
    chunk_a = CircularExtraction(
        circular_id=1,
        extraction_meta=ExtractionMeta(extractor="test", notes=["redshift_bound: z <= 1.61"]),
    )
    chunk_b = CircularExtraction(
        circular_id=1,
        extraction_meta=ExtractionMeta(extractor="test", notes=["something else"]),
    )
    merged = merge_extractions(1, [chunk_a, chunk_b], run_meta)
    assert "redshift_bound: z <= 1.61" in merged.extraction_meta.notes
    assert "something else" in merged.extraction_meta.notes


def test_merge_dedupes_identical_notes() -> None:
    run_meta = ExtractionMeta(extractor="test")
    chunk_a = CircularExtraction(
        circular_id=1,
        extraction_meta=ExtractionMeta(extractor="test", notes=["dup"]),
    )
    chunk_b = CircularExtraction(
        circular_id=1,
        extraction_meta=ExtractionMeta(extractor="test", notes=["dup"]),
    )
    merged = merge_extractions(1, [chunk_a, chunk_b], run_meta)
    assert merged.extraction_meta.notes.count("dup") == 1


def test_merge_preserves_run_level_notes_from_caller_meta() -> None:
    """Notes already on the caller-supplied run meta are kept, then chunk notes appended."""
    run_meta = ExtractionMeta(extractor="test", notes=["run-level"])
    chunk = CircularExtraction(
        circular_id=1,
        extraction_meta=ExtractionMeta(extractor="test", notes=["chunk-level"]),
    )
    merged = merge_extractions(1, [chunk], run_meta)
    assert merged.extraction_meta.notes == ["run-level", "chunk-level"]


def test_merge_carries_provenance_from_chunks() -> None:
    run_meta = ExtractionMeta(extractor="test")
    chunk_a = CircularExtraction(
        circular_id=1,
        provenance={"redshift": Span(start=0, end=9, snippet="z = 0.215")},
        extraction_meta=ExtractionMeta(extractor="test"),
    )
    chunk_b = CircularExtraction(
        circular_id=1,
        provenance={"event": Span(start=10, end=20, snippet="GRB 240101A")},
        extraction_meta=ExtractionMeta(extractor="test"),
    )
    merged = merge_extractions(1, [chunk_a, chunk_b], run_meta)
    assert set(merged.provenance.keys()) == {"redshift", "event"}
    assert merged.provenance["redshift"].snippet == "z = 0.215"


def test_merge_provenance_first_chunk_wins_on_key_collision() -> None:
    """When two chunks claim the same path, the first-seen span is kept."""
    run_meta = ExtractionMeta(extractor="test")
    chunk_a = CircularExtraction(
        circular_id=1,
        provenance={"redshift": Span(start=0, end=9, snippet="z = 0.215")},
        extraction_meta=ExtractionMeta(extractor="test"),
    )
    chunk_b = CircularExtraction(
        circular_id=1,
        provenance={"redshift": Span(start=50, end=59, snippet="z = 0.999")},
        extraction_meta=ExtractionMeta(extractor="test"),
    )
    merged = merge_extractions(1, [chunk_a, chunk_b], run_meta)
    assert merged.provenance["redshift"].snippet == "z = 0.215"
