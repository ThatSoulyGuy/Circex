"""Serialization roundtrip tests for every schema model."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from circex.schema import (
    CircularExtraction,
    Classification,
    DateTime,
    Event,
    ExtractionMeta,
    FollowUp,
    Localization,
    PhotometryExt,
    Redshift,
    Reporter,
    SpectralLine,
    SpectralLines,
    TimeOffset,
)

MODELS_AND_EXAMPLES: list[tuple[type[BaseModel], dict[str, object]]] = [
    (Event, {"event_name": "GRB 170817A", "id": "bn170817529"}),
    (Event, {"event_name": ["GRB 170817A", "GW170817", "AT2017gfo"]}),
    (FollowUp, {"ref_type": "GW", "ref_instrument": "LVK", "ref_ID": "S190425z"}),
    (Localization, {"ra": 197.45, "dec": -23.38, "ra_dec_error": 0.0001}),
    (Localization, {"ra": 100.0, "dec": 10.0, "ra_dec_error": [0.5, 0.3, 45.0]}),
    (DateTime, {"trigger_time": "2017-08-17T12:41:04.4Z", "observation_livetime": 600.0}),
    (
        PhotometryExt,
        {
            "filter": "r",
            "mag": 18.42,
            "mag_error": 0.05,
            "mag_system": "AB",
            "telescope": "Pan-STARRS1",
            "calibration_reference": "PS1",
            "seeing": 0.9,
            "airmass": 1.4,
        },
    ),
    (PhotometryExt, {"filter": "R", "limiting_mag": 21.5, "limiting_mag_sigma": 3.0}),
    (Redshift, {"redshift": 0.0095, "redshift_measure": "spectroscopic", "redshift_type": "host"}),
    (Reporter, {"mission": "Pan-STARRS", "instrument": "PS1", "messenger": "EM"}),
    (
        Reporter,
        {"mission": "LVK", "messenger": "GW", "spectral_band": [10.0, 1000.0],
         "spectral_band_units": "MHz"},
    ),
    (TimeOffset, {"value": 234.0, "unit": "s", "reference": "T+"}),
    (
        SpectralLine,
        {"line_id": "Halpha", "rest_wavelength": 6562.8, "observed_wavelength": 6625.3,
         "equivalent_width": -3.2},
    ),
    (
        SpectralLines,
        [
            {"line_id": "Halpha", "rest_wavelength": 6562.8},
            {"line_id": "OIII 5007", "rest_wavelength": 5007.0},
        ],
    ),
    (
        ExtractionMeta,
        {"extractor": "claude-haiku-4-5", "model_id": "claude-haiku-4-5-20251001",
         "prompt_version": "PROMPT_V1", "tokens_in": 1500, "tokens_out": 320,
         "latency_ms": 850.0, "cost_usd": 0.0024, "cache_hit": False},
    ),
    (
        ExtractionMeta,
        {"extractor": "regex-v1"},
    ),
]


@pytest.mark.parametrize("model_cls, example", MODELS_AND_EXAMPLES)
def test_model_roundtrip(model_cls: type[BaseModel], example: object) -> None:
    instance = model_cls.model_validate(example)
    dumped = instance.model_dump(mode="json", exclude_none=True)
    rebuilt = model_cls.model_validate(dumped)
    assert rebuilt == instance


def test_circular_extraction_minimal() -> None:
    ce = CircularExtraction.model_validate(
        {"circular_id": 12345, "extraction_meta": {"extractor": "regex-v1"}}
    )
    assert ce.circular_id == 12345
    assert ce.event is None
    assert ce.photometry == []
    assert ce.time_offsets == []


def test_circular_extraction_full_roundtrip() -> None:
    payload = {
        "circular_id": 33123,
        "event": {"event_name": "GRB 230307A"},
        "datetime": {"trigger_time": "2023-03-07T15:44:06Z"},
        "time_offsets": [{"value": 100.0, "unit": "s", "reference": "T+"}],
        "photometry": [
            {"filter": "r", "mag": 19.1, "mag_error": 0.05, "mag_system": "AB",
             "telescope": "ZTF", "instrument": "ZTF Camera"}
        ],
        "redshift": {"redshift": 0.065, "redshift_measure": "spectroscopic",
                     "redshift_type": "host"},
        "extraction_meta": {"extractor": "claude-haiku-4-5"},
    }
    ce = CircularExtraction.model_validate(payload)
    dumped = ce.model_dump(mode="json", by_alias=True, exclude_none=True)
    rebuilt = CircularExtraction.model_validate(dumped)
    assert rebuilt.event is not None and rebuilt.event.event_name == "GRB 230307A"
    assert len(rebuilt.photometry) == 1


def test_photometry_mag_system_enum_rejects_unknown() -> None:
    with pytest.raises(ValidationError):
        PhotometryExt.model_validate({"mag_system": "Other"})


def test_classification_rejects_unknown_class() -> None:
    with pytest.raises(ValidationError):
        Classification.model_validate({"classification": "DefinitelyNotARealClass"})


def test_classification_accepts_canonical() -> None:
    # "Ia" is a canonical class in supernovae.yaml — use it directly.
    instance = Classification.model_validate({"classification": "Ia"})
    assert instance.classification == "Ia"
