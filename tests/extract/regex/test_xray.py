"""X-ray energy-flux parsing, the instrument crosswalk, and flux-space mapping."""

from __future__ import annotations

import pytest

from circex.bot.skyportal_map import energy_flux_to_ujy, to_actions
from circex.extract.regex.xray import (
    bandpass_for_band,
    bandpass_for_instrument,
    parse_xray_with_spans,
)
from circex.schema import (
    CircularExtraction,
    Event,
    ExtractionMeta,
    Localization,
    PhotometryExt,
)

# GCN 45497, an EP-FXT non-detection.
GCN_45497 = (
    "EP-FXT performed a follow-up observation of EP260901a (Liang et al., GCN 45487) "
    "starting at 2026-09-01T22:26:36 (UTC), approximately 17 hours after the WXT "
    "detection. With an exposure time of 4 ks, no significant X-ray source was "
    "detected within the 2.4 arcmin radius of the EP-WXT position. The derived "
    "0.5-10 keV upper limit is about 1.0e-13 erg cm^-2 s^-1."
)


def test_an_upper_limit_carries_its_band_and_instrument() -> None:
    rows = [row for row, _ in parse_xray_with_spans(GCN_45497)]
    assert len(rows) == 1
    row = rows[0]
    assert row.is_detection is False
    assert row.limiting_energy_flux == 1e-13
    assert row.energy_band_kev == [0.5, 10.0]
    assert row.bandpass == "epfxt"


def test_the_observing_instrument_wins_over_one_named_for_context() -> None:
    """45497 quotes the EP-WXT position; the flux is FXT's."""
    assert bandpass_for_instrument(GCN_45497) == "epfxt"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Swift/XRT observed the field", "swiftxrt"),
        ("SVOM/MXT began observing", "svommxt"),
        ("the ECLAIRs trigger", "svomeclairs"),
        ("NICER observations", "nicerxti"),
    ],
)
def test_instruments_map_to_their_bandpass(text: str, expected: str) -> None:
    assert bandpass_for_instrument(text) == expected


def test_the_band_fallback_never_names_a_spacecraft() -> None:
    """A quoted 0.3-10 keV range is not evidence that EP observed it."""
    assert bandpass_for_band(0.3, 10.0) == "swiftxrt"


@pytest.mark.parametrize(
    "text",
    [
        # a fluence carries no per-second term
        "The burst had a fluence of 9x10^-7 erg/cm^2 in the 10-1000 keV band.",
        # a luminosity carries no per-area term
        "This corresponds to a 0.3-10 keV luminosity of 2e44 erg/s.",
    ],
)
def test_fluence_and_luminosity_are_not_photometry(text: str) -> None:
    assert parse_xray_with_spans(text) == []


def test_a_quoted_uncertainty_is_not_read_as_the_value() -> None:
    rows = [
        row
        for row, _ in parse_xray_with_spans(
            "Peak Flux: 3.5e-12 +/- 2.1e-12 erg cm^-2 s^-1 (0.3-10 keV) from Swift/XRT."
        )
    ]
    assert rows[0].energy_flux == 3.5e-12


def test_an_asymmetric_error_does_not_split_the_exponent() -> None:
    """'2.6 (+1.1, -0.9) e-14' is one number, not a 2.6 followed by a 14."""
    rows = [
        row
        for row, _ in parse_xray_with_spans(
            "The XRT count rate corresponds to a 0.3-10 keV flux of "
            "2.6 (+1.1, -0.9) e-14 erg/cm^2/s."
        )
    ]
    assert rows[0].energy_flux == pytest.approx(2.6e-14)


def test_energy_flux_converts_to_a_band_averaged_flux_density() -> None:
    # 1e-13 erg/cm2/s spread over 0.5-10 keV
    assert energy_flux_to_ujy(1e-13, [0.5, 10.0]) == pytest.approx(4.353e-3, rel=1e-3)


@pytest.mark.parametrize("band", [[10.0, 0.5], [1.0], [0.0, 10.0]])
def test_an_unusable_band_converts_to_nothing(band: list[float]) -> None:
    assert energy_flux_to_ujy(1e-13, band) is None


def _extraction(row: PhotometryExt) -> CircularExtraction:
    return CircularExtraction(
        circular_id=45497,
        event=Event(event_name="EP260901a"),
        localization=Localization(ra=10.0, dec=-20.0, ra_dec_error=0.0005),
        photometry=[row],
        extraction_meta=ExtractionMeta(extractor="regex"),
    )


def test_an_xray_limit_becomes_a_null_flux_point() -> None:
    row = PhotometryExt(
        energy_band_kev=[0.5, 10.0],
        limiting_energy_flux=1e-13,
        limiting_mag_sigma=3.0,
        bandpass="epfxt",
        obs_mjd=61284.9,
    )
    payload = to_actions(_extraction(row), default_instrument_id=9).photometry[0].to_payload()
    assert payload["flux"] is None
    assert payload["fluxerr"] == pytest.approx(4.353e-3 / 3.0, rel=1e-3)
    assert payload["zp"] == 23.9
    assert payload["filter"] == "epfxt"


def test_an_xray_detection_keeps_the_original_flux_in_altdata() -> None:
    row = PhotometryExt(
        energy_band_kev=[0.3, 10.0],
        energy_flux=3.5e-12,
        energy_flux_error=2.1e-12,
        bandpass="swiftxrt",
        obs_mjd=61284.9,
    )
    point = to_actions(_extraction(row), default_instrument_id=9).photometry[0]
    assert point.altdata["energy_flux_cgs"] == 3.5e-12
    assert point.altdata["energy_band_kev"] == [0.3, 10.0]


def test_a_bandpass_routes_to_its_own_instrument() -> None:
    """EP carries both WXT and FXT, so a telescope-keyed map cannot separate them."""
    row = PhotometryExt(
        energy_band_kev=[0.5, 10.0],
        limiting_energy_flux=1e-13,
        bandpass="epfxt",
        obs_mjd=61284.9,
    )
    actions = to_actions(
        _extraction(row),
        bandpass_instrument_map={"epwxt": 1183, "epfxt": 1184},
        default_instrument_id=1180,
    )
    assert actions.photometry[0].instrument_id == 1184


def test_an_unmapped_bandpass_still_falls_back_to_the_default() -> None:
    row = PhotometryExt(
        energy_band_kev=[0.5, 10.0],
        limiting_energy_flux=1e-13,
        bandpass="epfxt",
        obs_mjd=61284.9,
    )
    actions = to_actions(_extraction(row), default_instrument_id=1180)
    point = actions.photometry[0]
    assert point.instrument_id == 1180
    assert point.altdata["instrument_fallback"] is True
