"""Tests for circex.label.to_label_fields (snippet-paired value map)."""

from __future__ import annotations

from circex.label import backfill_spans, to_label_fields
from circex.schema import (
    CircularExtraction,
    Classification,
    Event,
    ExtractionMeta,
    Localization,
    PhotometryExt,
    Redshift,
    Span,
)


def _ex() -> CircularExtraction:
    return CircularExtraction(
        circular_id=1,
        event=Event(event_name="AT2026xyz"),
        localization=Localization(ra=224.512, dec=28.804),
        redshift=Redshift(redshift=0.512, redshift_type="host"),
        classification=Classification(classification="Ia"),
        photometry=[PhotometryExt(filter="r", bandpass="sdssr", mag=20.42, obs_mjd=61201.0)],
        provenance={
            "event": Span(start=0, end=9, snippet="AT2026xyz"),
            "localization": Span(start=20, end=47, snippet="RA = 224.512, Dec = +28.804"),
            "redshift": Span(start=60, end=69, snippet="z = 0.512"),
            "classification": Span(start=80, end=82, snippet="Ia"),
            "photometry[0]": Span(start=90, end=110, snippet="r  20.42  obs"),
        },
        extraction_meta=ExtractionMeta(extractor="regex-v1"),
    )


def test_pairs_value_with_snippet() -> None:
    f = to_label_fields(_ex())
    assert f["redshift.redshift"]["value"] == "0.512"
    assert f["redshift.redshift"]["snippet"] == "z = 0.512"
    assert f["redshift.redshift"]["start"] == 60


def test_backfill_spans_recovers_unique_matches_only() -> None:
    # An LLM-style extraction with NO provenance at all.
    ex = CircularExtraction(
        circular_id=1,
        redshift=Redshift(redshift=0.512),
        classification=Classification(classification="Tidal Disruption Event"),
        photometry=[
            PhotometryExt(filter="g", bandpass="sdssg", mag=19.7),  # 19.7 unique -> span
            PhotometryExt(filter="r", bandpass="sdssr", mag=20.5),  # 20.5 repeats -> no span
        ],
        provenance={},
        extraction_meta=ExtractionMeta(extractor="llama-server:mistral-7b"),
    )
    body = (
        "The transient at z = 0.512 is classified as a Tidal Disruption Event. "
        "Photometry: g = 19.7 mag; r = 20.5 mag; a nearby star at 20.5 mag."
    )
    added = backfill_spans(ex, body)

    f = to_label_fields(ex)
    # unique values recovered
    assert f["redshift.redshift"]["snippet"] and "z = 0.512" in f["redshift.redshift"]["snippet"]
    assert "Tidal Disruption Event" in f["classification.classification"]["snippet"]
    assert "19.7" in f["photometry[0].mag"]["snippet"]
    # ambiguous value (20.5 appears twice) left without a snippet
    assert f["photometry[1].mag"]["snippet"] is None
    assert added >= 3


def test_parent_span_covers_leaf_fields() -> None:
    """A leaf without its own provenance inherits the parent object's span."""
    f = to_label_fields(_ex())
    # localization.ra / .dec both fall back to the 'localization' object span
    assert f["localization.ra"]["snippet"] == "RA = 224.512, Dec = +28.804"
    assert f["localization.dec"]["snippet"] == "RA = 224.512, Dec = +28.804"


def test_photometry_rows_are_indexed_and_snippeted() -> None:
    f = to_label_fields(_ex())
    assert f["photometry[0].mag"]["value"] == "20.42"
    assert f["photometry[0].mag"]["snippet"] == "r  20.42  obs"
    assert f["photometry[0].bandpass"]["value"] == "sdssr"


def test_value_without_provenance_has_null_snippet() -> None:
    ex = CircularExtraction(
        circular_id=1,
        redshift=Redshift(redshift=0.3),  # no provenance recorded
        extraction_meta=ExtractionMeta(extractor="regex-v1"),
    )
    f = to_label_fields(ex)
    assert f["redshift.redshift"]["value"] == "0.3"
    assert f["redshift.redshift"]["snippet"] is None


def test_meta_and_provenance_are_excluded() -> None:
    f = to_label_fields(_ex())
    assert not any(k.startswith("extraction_meta") or k.startswith("provenance") for k in f)
    assert "circular_id" not in f


def test_event_name_list_is_joined() -> None:
    ex = CircularExtraction(
        circular_id=1,
        event=Event(event_name=["GW170817", "AT2017gfo"]),
        extraction_meta=ExtractionMeta(extractor="regex-v1"),
    )
    f = to_label_fields(ex)
    assert f["event.event_name"]["value"] == "GW170817, AT2017gfo"
