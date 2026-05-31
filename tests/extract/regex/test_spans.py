"""Tests for span-level provenance in the regex extractor.

Covers: the Span model itself, that each regex sub-parser's spans-aware variant
returns offsets that resolve back to the snippet, and that the assembled
RegexExtractor populates CircularExtraction.provenance with the expected keys
and self-consistent body[start:end] snippets.
"""

from __future__ import annotations

from circex.extract.protocol import Circular
from circex.extract.regex import RegexExtractor
from circex.extract.regex.classification import parse_classification_with_span
from circex.extract.regex.coords import parse_coords_with_span
from circex.extract.regex.dates import parse_time_offsets_with_spans
from circex.extract.regex.mag_table import (
    parse_mag_table_with_spans,
    parse_single_mags_with_spans,
)
from circex.extract.regex.redshift import parse_redshift_with_span
from circex.schema import Span


def _circular(body: str, subject: str = "Subj", event_id: str | None = None) -> Circular:
    return Circular(circular_id=1, subject=subject, body=body, event_id=event_id)


# ---- Span model ----


def test_span_validates_and_roundtrips() -> None:
    s = Span(start=3, end=8, snippet="hello")
    assert s.start == 3 and s.end == 8 and s.snippet == "hello"


# ---- Per-parser spans resolve to their snippet ----


def test_redshift_span_resolves_to_snippet() -> None:
    body = "Spectroscopy gives z = 1.234 ± 0.005 today."
    result = parse_redshift_with_span(body)
    assert result is not None
    _, span = result
    assert body[span.start:span.end] == span.snippet
    assert "1.234" in span.snippet


def test_coords_span_resolves_to_snippet() -> None:
    body = "Position: RA = 191.532, Dec = -23.7534 (J2000)."
    result = parse_coords_with_span(body)
    assert result is not None
    _, span = result
    assert body[span.start:span.end] == span.snippet
    assert "RA" in span.snippet and "Dec" in span.snippet


def test_classification_span_resolves_to_snippet() -> None:
    body = "Spectroscopic typing indicates SNIa from broad lines."
    result = parse_classification_with_span(body)
    assert result is not None
    _, span = result
    assert body[span.start:span.end] == span.snippet


def test_time_offsets_spans_resolve_to_snippets() -> None:
    body = "First epoch at T+234s, later T+1500 sec."
    hits = parse_time_offsets_with_spans(body)
    assert len(hits) == 2
    for _, span in hits:
        assert body[span.start:span.end] == span.snippet


def test_single_mag_span_resolves_to_snippet() -> None:
    body = "We measured r = 18.42 ± 0.05 in the optical."
    hits = parse_single_mags_with_spans(body)
    assert hits, "expected a magnitude hit"
    _, span = hits[0]
    assert body[span.start:span.end] == span.snippet
    assert "18.42" in span.snippet


def test_mag_table_spans_resolve_to_per_row_snippets() -> None:
    body = (
        "Date          Filter   Mag      Err\n"
        "2020-01-01    r        19.10    0.05\n"
        "2020-01-02    g        19.21    0.07\n"
    )
    hits = parse_mag_table_with_spans(body)
    assert len(hits) == 2
    for row, span in hits:
        assert body[span.start:span.end] == span.snippet
        assert str(row.mag) in span.snippet


# ---- End-to-end RegexExtractor.provenance ----


def test_extractor_populates_provenance_for_redshift() -> None:
    body = "Host galaxy emission gives z = 0.198 from spectroscopy."
    r = RegexExtractor().extract(_circular(body))
    assert "redshift" in r.provenance
    p = r.provenance["redshift"]
    assert body[p.start:p.end] == p.snippet


def test_extractor_populates_provenance_for_localization() -> None:
    body = "Astrometry: RA = 100.5, Dec = +12.5 (J2000)."
    r = RegexExtractor().extract(_circular(body))
    assert "localization" in r.provenance
    p = r.provenance["localization"]
    assert body[p.start:p.end] == p.snippet


def test_extractor_populates_provenance_for_table_rows() -> None:
    body = (
        "Date          Filter   Mag      Err\n"
        "2020-01-01    r        19.10    0.05\n"
        "2020-01-02    r        19.21    0.05\n"
    )
    r = RegexExtractor().extract(_circular(body))
    assert "photometry[0]" in r.provenance and "photometry[1]" in r.provenance
    for key in ("photometry[0]", "photometry[1]"):
        p = r.provenance[key]
        assert body[p.start:p.end] == p.snippet


def test_extractor_populates_provenance_for_time_offsets() -> None:
    body = "We began at T+234s and finished by T+1500 sec."
    r = RegexExtractor().extract(_circular(body))
    assert "time_offsets[0]" in r.provenance
    assert "time_offsets[1]" in r.provenance
    for key in ("time_offsets[0]", "time_offsets[1]"):
        p = r.provenance[key]
        assert body[p.start:p.end] == p.snippet


def test_extractor_populates_provenance_for_follow_up() -> None:
    body = "Following GCN #205, see also GCN Circular 213 for details."
    r = RegexExtractor().extract(_circular(body))
    assert "follow_up" in r.provenance
    p = r.provenance["follow_up"]
    assert body[p.start:p.end] == p.snippet
    assert "205" in p.snippet and "213" in p.snippet


def test_extractor_provenance_for_event_from_body() -> None:
    # eventId and subject are empty so the primary event comes from body — only
    # body-sourced events get provenance spans.
    body = "Optical follow-up of GRB 230307A from our telescope."
    r = RegexExtractor().extract(_circular(body, subject="No event in subject"))
    assert r.event is not None
    assert "event" in r.provenance
    p = r.provenance["event"]
    assert body[p.start:p.end] == p.snippet
    assert "GRB" in p.snippet


def test_extractor_provenance_empty_when_no_matches() -> None:
    r = RegexExtractor().extract(_circular("Nothing to extract here."))
    assert r.provenance == {}


def test_extractor_classification_provenance() -> None:
    body = "Spectroscopic typing indicates SNIa from broad lines."
    r = RegexExtractor().extract(_circular(body))
    assert "classification" in r.provenance
    p = r.provenance["classification"]
    assert body[p.start:p.end] == p.snippet
