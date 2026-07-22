"""Tests for HybridExtractor per-field routing (regex + constrained LLM)."""

from __future__ import annotations

from typing import Any

from circex.extract.hybrid import HybridExtractor
from circex.extract.protocol import Circular
from circex.schema import CircularExtraction


def _mk(**fields: Any) -> CircularExtraction:
    base: dict[str, Any] = {"circular_id": 1, "extraction_meta": {"extractor": "x"}}
    base.update(fields)
    return CircularExtraction.model_validate(base)


class _Fake:
    def __init__(self, extraction: CircularExtraction, extractor_id: str) -> None:
        self._extraction = extraction
        self.extractor_id = extractor_id

    def extract(self, circular: Circular) -> CircularExtraction:
        return self._extraction


def test_hybrid_routes_each_field_to_its_owner() -> None:
    regex_ex = _mk(
        event={"event_name": "GRB 260604C"},
        localization={"ra": 224.4566, "dec": 28.8175},
        classification={"classification": "Orion"},  # regex contaminant — must be dropped
        provenance={
            "event": {"start": 0, "end": 11, "snippet": "GRB 260604C"},
            "localization": {"start": 10, "end": 40, "snippet": "RA=224.4566 Dec=+28.8175"},
        },
    )
    llm_ex = _mk(
        event={"event_name": "WRONG"},  # regex owns event; this must lose
        photometry=[{"mag": 19.2}],
        redshift={"redshift": 0.5},
        classification={"classification": "Ia"},
        provenance={
            "photometry[0]": {"start": 50, "end": 58, "snippet": "r = 19.2"},
            "redshift": {"start": 70, "end": 77, "snippet": "z = 0.5"},
        },
    )
    hybrid = HybridExtractor(_Fake(regex_ex, "regex-v1"), _Fake(llm_ex, "llama-server:mistral-7b"))
    m = hybrid.extract(Circular(circular_id=1, subject="", body="..."))

    # regex owns event name and coordinates
    assert m.event is not None and m.event.event_name == "GRB 260604C"
    assert m.localization is not None and m.localization.ra == 224.4566
    # LLM owns photometry, redshift, classification (regex's "Orion" is dropped)
    assert m.photometry[0].mag == 19.2
    assert m.redshift is not None and m.redshift.redshift == 0.5
    assert m.classification is not None and m.classification.classification == "Ia"
    # provenance travels with whichever extractor supplied the field
    assert m.provenance["localization"].snippet == "RA=224.4566 Dec=+28.8175"
    assert m.provenance["photometry[0]"].snippet == "r = 19.2"
    assert m.provenance["redshift"].snippet == "z = 0.5"
    assert m.extraction_meta.extractor.startswith("hybrid:")


def test_hybrid_falls_back_to_secondary_when_primary_is_empty() -> None:
    # redshift routes llm -> regex; with the LLM silent, regex fills it in.
    regex_ex = _mk(
        redshift={"redshift": 1.2},
        provenance={"redshift": {"start": 0, "end": 6, "snippet": "z=1.2"}},
    )
    hybrid = HybridExtractor(_Fake(regex_ex, "regex-v1"), _Fake(_mk(), "llm"))
    m = hybrid.extract(Circular(circular_id=1, subject="", body="x"))

    assert m.redshift is not None and m.redshift.redshift == 1.2
    assert m.provenance["redshift"].snippet == "z=1.2"


def test_hybrid_drops_llm_only_fields_when_regex_is_the_lone_source() -> None:
    # classification is LLM-only: a regex-supplied classification must never appear.
    regex_ex = _mk(classification={"classification": "RS CVn"})
    hybrid = HybridExtractor(_Fake(regex_ex, "regex-v1"), _Fake(_mk(), "llm"))
    m = hybrid.extract(Circular(circular_id=1, subject="", body="x"))

    assert m.classification is None


def test_hybrid_routing_override_keeps_classifier_fallback() -> None:
    # The consumer's SN-type classifier writes through the regex side; with the
    # override, its classification survives when the LLM abstains.
    regex_ex = _mk(classification={"classification": "Ia"})
    hybrid = HybridExtractor(
        _Fake(regex_ex, "regex-v1"),
        _Fake(_mk(), "llm"),
        routing_overrides={"classification": ("llm", "regex")},
    )
    m = hybrid.extract(Circular(circular_id=1, subject="", body="x"))

    assert m.classification is not None and m.classification.classification == "Ia"
