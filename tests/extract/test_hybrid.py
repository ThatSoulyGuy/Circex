"""Tests for HybridExtractor per-field routing (regex + constrained LLM)."""

from __future__ import annotations

from typing import Any

import pytest

from circex.extract.hybrid import _ROUTING, HybridExtractor
from circex.extract.protocol import Circular
from circex.schema import CircularExtraction, ExtractionMeta, PhotometryExt


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


def _stub(circular_id: int, **fields: object) -> CircularExtraction:
    return CircularExtraction(
        circular_id=circular_id,
        extraction_meta=ExtractionMeta(extractor="stub"),
        **fields,  # type: ignore[arg-type]
    )


class _Fixed:
    """Extractor returning a fixed extraction."""

    def __init__(self, result: CircularExtraction, name: str) -> None:
        self._result, self._name = result, name

    @property
    def extractor_id(self) -> str:
        return self._name

    def extract(self, circular: Circular) -> CircularExtraction:
        return self._result


def test_xray_row_survives_llm_prose_filter() -> None:
    # The LLM writes the band into `filter`; the structured regex row stands in.
    regex = _stub(
        1, photometry=[PhotometryExt(bandpass="epfxt", energy_band_kev=[0.5, 10.0], obs_mjd=6.0)]
    )
    llm = _stub(1, photometry=[PhotometryExt(filter="0.5-10 keV", obs_mjd=6.0)])
    merged = HybridExtractor(_Fixed(regex, "regex"), _Fixed(llm, "llm")).extract(
        Circular(circular_id=1, subject="s", body="b")
    )
    assert [r.bandpass for r in merged.photometry] == ["epfxt"]
    assert merged.photometry[0].energy_band_kev == [0.5, 10.0]


def test_optical_llm_rows_are_kept_alongside_rescued_rows() -> None:
    regex = _stub(
        1, photometry=[PhotometryExt(bandpass="epfxt", energy_band_kev=[0.5, 10.0], obs_mjd=6.0)]
    )
    llm = _stub(
        1,
        photometry=[
            PhotometryExt(filter="r", bandpass="sdssr", mag=20.0, obs_mjd=6.0),
            PhotometryExt(filter="0.5-10 keV", obs_mjd=6.0),
        ],
    )
    merged = HybridExtractor(_Fixed(regex, "regex"), _Fixed(llm, "llm")).extract(
        Circular(circular_id=1, subject="s", body="b")
    )
    assert sorted(r.bandpass or "" for r in merged.photometry) == ["epfxt", "sdssr"]


def test_retraction_flag_survives_the_merge() -> None:
    regex = _stub(1, retraction=True)
    llm = _stub(1, photometry=[PhotometryExt(filter="r", mag=20.0)])
    merged = HybridExtractor(_Fixed(regex, "regex"), _Fixed(llm, "llm")).extract(
        Circular(circular_id=1, subject="Trigger 1 is not a GRB", body="b")
    )
    assert merged.retraction is True


def test_every_extraction_field_is_routed_or_handled() -> None:
    # A field absent from both sets is rebuilt at its default by the merge, which
    # looks like the extractor never found it.
    handled = set(_ROUTING) | {"circular_id", "provenance", "extraction_meta", "retraction"}
    assert set(CircularExtraction.model_fields) - handled == set()


def test_telescope_survives_the_llm_owning_photometry() -> None:
    # The LLM's rows carry no telescope; the one regex read from the prose stands.
    regex = _stub(
        1,
        photometry=[
            PhotometryExt(filter="r", mag=20.0, telescope="Keck-II", telescope_canonical="Keck")
        ],
    )
    llm = _stub(1, photometry=[PhotometryExt(filter="r", mag=20.1, obs_mjd=6.0)])
    merged = HybridExtractor(_Fixed(regex, "regex"), _Fixed(llm, "llm")).extract(
        Circular(circular_id=1, subject="s", body="b")
    )
    assert [r.telescope for r in merged.photometry] == ["Keck-II"]
    assert merged.photometry[0].mag == 20.1


def test_a_telescope_the_llm_named_is_kept() -> None:
    regex = _stub(1, photometry=[PhotometryExt(filter="r", telescope="Keck-II")])
    llm = _stub(1, photometry=[PhotometryExt(filter="r", telescope="Subaru")])
    merged = HybridExtractor(_Fixed(regex, "regex"), _Fixed(llm, "llm")).extract(
        Circular(circular_id=1, subject="s", body="b")
    )
    assert [r.telescope for r in merged.photometry] == ["Subaru"]


def test_the_prose_names_the_telescope_when_regex_found_no_rows() -> None:
    # Regex parsed no photometry, so it has no row to carry a telescope from;
    # the name is still in the body.
    regex = _stub(1)
    llm = _stub(1, photometry=[PhotometryExt(filter="r", mag=20.0)])
    merged = HybridExtractor(_Fixed(regex, "regex"), _Fixed(llm, "llm")).extract(
        Circular(
            circular_id=1,
            subject="s",
            body="We observed the field at the Keck-II telescope on UT 1998 June 16.",
        )
    )
    assert merged.photometry[0].telescope == "Keck-II"
    assert merged.photometry[0].telescope_canonical == "Keck"


def test_a_stated_epoch_overrides_a_generated_one() -> None:
    # GCN 45501: the model emitted a well-formed MJD four years off; the body
    # states the observation time, and that is the one to keep.
    body = "Our observation started on 2026-09-03T13:06:41.486 UT (29.36 min after the trigger)."
    regex = _stub(1)
    llm = _stub(
        1,
        photometry=[
            PhotometryExt(filter="r", mag=17.91, obs_mjd=59868.0, obs_time="2022-10-16T00:00:00Z")
        ],
    )
    merged = HybridExtractor(_Fixed(regex, "regex"), _Fixed(llm, "llm")).extract(
        Circular(circular_id=45501, subject="s", body=body)
    )
    assert merged.photometry[0].obs_mjd == pytest.approx(61286.546, abs=1e-3)
    assert merged.photometry[0].obs_time.startswith("2026-09-03")


def test_rows_keep_their_epoch_when_the_body_states_none() -> None:
    llm = _stub(1, photometry=[PhotometryExt(filter="r", mag=20.0, obs_mjd=61200.5)])
    merged = HybridExtractor(_Fixed(_stub(1), "regex"), _Fixed(llm, "llm")).extract(
        Circular(circular_id=1, subject="s", body="No time is given here.")
    )
    assert merged.photometry[0].obs_mjd == 61200.5
