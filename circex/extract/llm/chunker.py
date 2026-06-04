"""Chunking for long circular bodies + deterministic merge.

If body is short enough, returns one chunk identical to single-pass. If long,
splits on paragraph boundaries with overlap. The merge is deterministic:
- list fields (photometry, time_offsets): union (dedupe by tuple key)
- scalar fields (event, redshift, etc.): first non-null wins, ties logged
- extraction_meta: aggregates tokens, latency

The merge invariant: chunk_then_merge(short_body) == single_pass(short_body).
"""

from __future__ import annotations

from circex.schema import (
    CircularExtraction,
    Event,
    ExtractionMeta,
    FollowUp,
    Localization,
    PhotometryExt,
    Redshift,
    Reporter,
    SpectralLines,
)
from circex.schema.classification import Classification
from circex.schema.datetime_ import DateTime
from circex.schema.time_offset import TimeOffset

# Default character threshold — tuned to leave headroom under Claude Haiku's
# context after preamble + few-shots. ~30k chars ≈ ~7.5k tokens.
DEFAULT_CHUNK_THRESHOLD = 30_000
DEFAULT_CHUNK_SIZE = 20_000
DEFAULT_OVERLAP = 1_500


def chunk_body(
    body: str,
    threshold: int = DEFAULT_CHUNK_THRESHOLD,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Split a body into chunks on paragraph boundaries.

    For short bodies (len <= threshold), returns a single-element list containing
    the whole body — so single-pass extraction is byte-identical to chunked.
    """
    if len(body) <= threshold:
        return [body]

    paragraphs = body.split("\n\n")
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if not current:
            current = para
            continue
        if len(current) + len(para) + 2 <= chunk_size:
            current = current + "\n\n" + para
        else:
            chunks.append(current)
            # Start next chunk with overlap from previous chunk tail.
            tail = current[-overlap:] if overlap > 0 else ""
            current = (tail + "\n\n" + para) if tail else para
    if current:
        chunks.append(current)
    return chunks


# ---------- Merge helpers ----------


def _photometry_key(p: PhotometryExt) -> tuple[object, ...]:
    return (p.filter, p.mag, p.limiting_mag, p.telescope, p.instrument)


def _time_offset_key(t: TimeOffset) -> tuple[object, ...]:
    return (t.value, t.unit, t.reference)


def _first_non_null[T](*candidates: T | None) -> T | None:
    for c in candidates:
        if c is not None:
            return c
    return None


def _merge_scalar[T](existing: T | None, candidate: T | None) -> T | None:
    return existing if existing is not None else candidate


def merge_extractions(
    circular_id: int,
    extractions: list[CircularExtraction],
    extraction_meta: ExtractionMeta,
) -> CircularExtraction:
    """Merge per-chunk CircularExtraction objects into one.

    Deterministic. For single-element input returns the same object's fields
    plus the supplied extraction_meta.
    """
    if not extractions:
        return CircularExtraction(circular_id=circular_id, extraction_meta=extraction_meta)

    event: Event | None = None
    follow_up: FollowUp | None = None
    localization: Localization | None = None
    datetime_: DateTime | None = None
    classification: Classification | None = None
    redshift: Redshift | None = None
    reporter: Reporter | None = None
    spectroscopy: SpectralLines | None = None

    photometry_seen: dict[tuple[object, ...], PhotometryExt] = {}
    time_offsets_seen: dict[tuple[object, ...], TimeOffset] = {}
    notes_seen: list[str] = []
    provenance_seen: dict[str, object] = {}

    for e in extractions:
        event = _merge_scalar(event, e.event)
        follow_up = _merge_scalar(follow_up, e.follow_up)
        localization = _merge_scalar(localization, e.localization)
        datetime_ = _merge_scalar(datetime_, e.datetime_)
        classification = _merge_scalar(classification, e.classification)
        redshift = _merge_scalar(redshift, e.redshift)
        reporter = _merge_scalar(reporter, e.reporter)
        spectroscopy = _merge_scalar(spectroscopy, e.spectroscopy)

        for p in e.photometry:
            key = _photometry_key(p)
            photometry_seen.setdefault(key, p)
        for t in e.time_offsets:
            key = _time_offset_key(t)
            time_offsets_seen.setdefault(key, t)
        for note in e.extraction_meta.notes:
            if note not in notes_seen:
                notes_seen.append(note)
        for path, span in e.provenance.items():
            provenance_seen.setdefault(path, span)

    # Carry per-chunk notes/provenance forward into the merged extraction's
    # extraction_meta (the caller's `extraction_meta` provides the run-level
    # fields like latency/tokens/cost; notes are content, not run-level).
    merged_meta = extraction_meta.model_copy(
        update={"notes": [*extraction_meta.notes, *notes_seen]}
    )

    return CircularExtraction.model_validate(
        {
            "circular_id": circular_id,
            "event": event,
            "follow_up": follow_up,
            "localization": localization,
            "datetime": datetime_,
            "classification": classification,
            "redshift": redshift,
            "reporter": reporter,
            "spectroscopy": spectroscopy,
            "photometry": list(photometry_seen.values()),
            "time_offsets": list(time_offsets_seen.values()),
            "provenance": provenance_seen,
            "extraction_meta": merged_meta,
        }
    )
