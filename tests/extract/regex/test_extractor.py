"""End-to-end tests for the composed RegexExtractor."""

from __future__ import annotations

from circex.extract.protocol import Circular
from circex.extract.regex import RegexExtractor


def _circular(circular_id: int, subject: str, body: str, event_id: str | None = None) -> Circular:
    return Circular(
        circular_id=circular_id,
        subject=subject,
        body=body,
        event_id=event_id,
    )


def test_extractor_id() -> None:
    assert RegexExtractor().extractor_id == "regex-v1"


def test_extracts_event_from_subject() -> None:
    c = _circular(1, "GRB 230307A optical follow-up", "Body text", event_id=None)
    r = RegexExtractor().extract(c)
    assert r.event is not None
    assert r.event.event_name == "GRB230307A"


def test_extracts_redshift_and_classification_together() -> None:
    body = (
        "Spectroscopic typing indicates SNIa. Host galaxy emission lines yield "
        "z = 0.0987 ± 0.0005."
    )
    r = RegexExtractor().extract(_circular(2, "GRB optical follow-up", body))
    assert r.redshift is not None and r.redshift.redshift == 0.0987
    assert r.classification is not None and r.classification.classification == "Ia"


def test_extracts_gcn_xrefs_into_follow_up() -> None:
    body = "Following up on the OT in GCN #205 (see also GCN Circular 213)."
    r = RegexExtractor().extract(_circular(3, "Follow-up", body))
    assert r.follow_up is not None
    assert "205" in str(r.follow_up.reference)
    assert "213" in str(r.follow_up.reference)


def test_extracts_localization() -> None:
    body = "RA = 191.532, Dec = -23.7534 (J2000)."
    r = RegexExtractor().extract(_circular(4, "Position", body))
    assert r.localization is not None
    assert abs(r.localization.ra - 191.532) < 1e-6
    assert abs(r.localization.dec - -23.7534) < 1e-6


def test_extracts_time_offsets() -> None:
    body = "First epoch began at T+234s and ended T+1500 sec."
    r = RegexExtractor().extract(_circular(5, "Photometry", body))
    assert len(r.time_offsets) == 2


def test_table_preferred_over_single_mag() -> None:
    body = """
Some prose mentions r = 18.5 in passing.

Date          Filter   Mag      Err
2020-01-01    r        19.10    0.05
2020-01-02    r        19.21    0.05
""".strip()
    r = RegexExtractor().extract(_circular(6, "Photometry", body))
    # The table wins: the prose 'r = 18.5' is not in the output.
    mags = {p.mag for p in r.photometry}
    assert 19.10 in mags and 19.21 in mags
    assert 18.5 not in mags


def test_meta_populated() -> None:
    r = RegexExtractor().extract(_circular(7, "Subj", "Body"))
    assert r.extraction_meta.extractor == "regex-v1"
    assert r.extraction_meta.latency_ms is not None
    assert r.extraction_meta.cache_hit is False


def test_empty_body_produces_valid_extraction() -> None:
    r = RegexExtractor().extract(_circular(8, "", ""))
    assert r.circular_id == 8
    assert r.event is None and r.photometry == []
