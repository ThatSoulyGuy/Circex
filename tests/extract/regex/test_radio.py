"""Radio flux-density parsing, the frequency crosswalk, and flux-space mapping."""

from __future__ import annotations

import pytest

from circex.bot.skyportal_map import ASSUMED_FLUX_ERROR_FRACTION, to_actions
from circex.extract.protocol import Circular
from circex.extract.regex.extractor import RegexExtractor
from circex.extract.regex.radio import (
    bandpass_for_frequency,
    normalize_flux_unit,
    parse_radio_with_spans,
    to_ujy,
)
from circex.schema import (
    CircularExtraction,
    Event,
    ExtractionMeta,
    Localization,
    PhotometryExt,
)

# GCN 33475, the shape that carries a detection and a limit in one circular.
GCN_33475 = (
    "We observed GRB 230703A (Fermi GBM Team GCN 33405) with the Australia Telescope\n"
    "Compact Array (ATCA) between 2023-03-12_02:30 UT and 2023-03-12_07:30 UT\n"
    "(~4.5 days post-burst). In our preliminary analysis, we detect a radio source\n"
    "coincident with the X-ray (Burrows et al. GCN 33429) and optical (Levan et al.\n"
    "GCN 33439) counterpart with a flux density of 120+/-30 microJy/beam at 9 GHz.\n"
    "We also obtain an 3 sigma upper limit of 90 microJy/beam at 5.5 GHz.\n"
)

# GCN 33433, where two flux densities are distributed over two frequencies.
GCN_33433 = (
    "The Australia Telescope Compact Array (ATCA) automatically triggered on\n"
    "the Swift-BAT detection of the short GRB 230217A at 5.5 and 9 GHz.\n"
    "At the position of the proposed counterpart, we detected a source at both\n"
    "5.5 GHz and 9 GHz with flux densities of 170 +/- 30 and 150 +/- 20\n"
    "microJy/beam, respectively.\n"
)


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("microJy/beam", "uJy"),
        ("micro Jy", "uJy"),
        ("uJy", "uJy"),
        ("μJy", "uJy"),
        ("mJy", "mJy"),
        ("Jy", "Jy"),
    ],
)
def test_unit_aliases_fold_to_the_enum(written: str, expected: str) -> None:
    assert normalize_flux_unit(written) == expected


def test_flux_density_converts_to_microjansky() -> None:
    assert to_ujy(1.0, "mJy") == 1000.0
    assert to_ujy(2.5, "Jy") == 2_500_000.0


@pytest.mark.parametrize(
    ("ghz", "expected"),
    [
        (5.5, "radio-6GHz"),
        (9.0, "radio-10GHz"),
        (1.284, "radio-1.4GHz"),
        (93.0, "radio-93GHz"),
        (230.0, "sma-230GHz"),
    ],
)
def test_frequency_maps_to_nearest_bandpass(ghz: float, expected: str) -> None:
    assert bandpass_for_frequency(ghz) == expected


@pytest.mark.parametrize("ghz", [0.05, 650.0])
def test_frequency_outside_every_band_has_no_bandpass(ghz: float) -> None:
    """Nothing is representable there, so the row is dropped rather than mislabelled."""
    assert bandpass_for_frequency(ghz) is None


def test_detection_and_upper_limit_in_one_circular() -> None:
    rows = [row for row, _ in parse_radio_with_spans(GCN_33475)]
    assert len(rows) == 2

    detection, limit = rows
    assert detection.is_detection is True
    assert (detection.flux_density, detection.flux_density_error) == (120.0, 30.0)
    assert detection.frequency_ghz == 9.0
    assert detection.bandpass == "radio-10GHz"

    assert limit.is_detection is False
    assert limit.limiting_flux_density == 90.0
    assert limit.limiting_mag_sigma == 3.0
    assert limit.frequency_ghz == 5.5


def test_respectively_pairs_values_with_frequencies_in_order() -> None:
    rows = [row for row, _ in parse_radio_with_spans(GCN_33433)]
    assert [(r.flux_density, r.frequency_ghz) for r in rows] == [(170.0, 5.5), (150.0, 9.0)]


def test_several_units_in_one_clause_yield_nothing() -> None:
    """A column table cannot be paired safely, so it is left to the LLM path."""
    text = "Flux Density 3-sigma Limit for SSS17a 8.5 GHz: 0.66 mJy 120 uJy 10.5 GHz: 0.54 mJy"
    assert parse_radio_with_spans(text) == []


def test_frequency_cited_for_comparison_is_not_borrowed() -> None:
    """The 15 GHz belongs to the instrument being compared against, not this row."""
    text = (
        "The afterglow is detected at a flux density of ~2 mJy, indicating that the peak "
        "emission is still at higher frequencies than the 15 GHz detection by AMI-LA."
    )
    assert parse_radio_with_spans(text) == []


def test_standalone_measurement_lines_are_parsed() -> None:
    text = "We report preliminary flux densities of:\n~0.6 mJy at 8.5 GHz\n~0.5 mJy at 10.5 GHz\n"
    rows = [row for row, _ in parse_radio_with_spans(text)]
    assert [(r.flux_density, r.frequency_ghz) for r in rows] == [(0.6, 8.5), (0.5, 10.5)]


def test_host_galaxy_flux_is_not_transient_photometry() -> None:
    text = "We detect the host galaxy at a flux density of 0.22 mJy at 6 GHz."
    assert parse_radio_with_spans(text) == []


def test_radio_rows_reach_the_extractor() -> None:
    extraction = RegexExtractor().extract(
        Circular(circular_id=33475, subject="GRB 230307A: ATCA radio detection", body=GCN_33475)
    )
    radio = [r for r in extraction.photometry if r.frequency_ghz is not None]
    assert len(radio) == 2
    assert all(r.obs_mjd is not None for r in radio), "the ATCA underscore date must resolve"


def _radio_extraction(row: PhotometryExt) -> CircularExtraction:
    return CircularExtraction(
        circular_id=1,
        event=Event(event_name="GRB 230307A"),
        localization=Localization(ra=10.0, dec=-20.0),
        photometry=[row],
        extraction_meta=ExtractionMeta(extractor="regex"),
    )


def test_detection_becomes_a_flux_space_point() -> None:
    row = PhotometryExt(
        frequency_ghz=9.0,
        flux_density=120.0,
        flux_density_error=30.0,
        flux_density_unit="uJy",
        obs_mjd=60015.1,
    )
    actions = to_actions(_radio_extraction(row), default_instrument_id=7)
    payload = actions.photometry[0].to_payload()
    assert payload["flux"] == 120.0
    assert payload["fluxerr"] == 30.0
    assert payload["zp"] == 23.9
    assert payload["filter"] == "radio-10GHz"
    assert "mag" not in payload


def test_upper_limit_becomes_a_null_flux_with_sigma_scaled_error() -> None:
    """SkyPortal derives the limiting magnitude from fluxerr, so the limit is divided by sigma."""
    row = PhotometryExt(
        frequency_ghz=5.5,
        limiting_flux_density=90.0,
        limiting_mag_sigma=3.0,
        flux_density_unit="uJy",
        obs_mjd=60015.1,
    )
    actions = to_actions(_radio_extraction(row), default_instrument_id=7)
    payload = actions.photometry[0].to_payload()
    assert payload["flux"] is None
    assert payload["fluxerr"] == 30.0


def test_millijansky_is_converted_to_microjansky() -> None:
    row = PhotometryExt(
        frequency_ghz=6.0,
        flux_density=2.0,
        flux_density_error=0.1,
        flux_density_unit="mJy",
        obs_mjd=60015.1,
    )
    actions = to_actions(_radio_extraction(row), default_instrument_id=7)
    payload = actions.photometry[0].to_payload()
    assert (payload["flux"], payload["fluxerr"]) == (2000.0, 100.0)


def test_detection_without_an_uncertainty_gets_a_flagged_nominal_error() -> None:
    """About half of radio detections quote no error; they are posted, but marked assumed."""
    row = PhotometryExt(
        frequency_ghz=9.0, flux_density=400.0, flux_density_unit="uJy", obs_mjd=60015.1
    )
    actions = to_actions(_radio_extraction(row), default_instrument_id=7)
    point = actions.photometry[0]
    payload = point.to_payload()
    assert payload["flux"] == 400.0
    assert payload["fluxerr"] == 400.0 * ASSUMED_FLUX_ERROR_FRACTION
    assert point.altdata["flux_density_error_assumed"] is True


def test_a_reported_uncertainty_is_never_marked_assumed() -> None:
    row = PhotometryExt(
        frequency_ghz=9.0,
        flux_density=400.0,
        flux_density_error=25.0,
        flux_density_unit="uJy",
        obs_mjd=60015.1,
    )
    point = to_actions(_radio_extraction(row), default_instrument_id=7).photometry[0]
    assert point.to_payload()["fluxerr"] == 25.0
    assert "flux_density_error_assumed" not in point.altdata


def test_the_extraction_itself_keeps_the_uncertainty_null() -> None:
    """The nominal error is a write-time policy; the stored extraction stays truthful."""
    rows = [row for row, _ in parse_radio_with_spans("A flux density of ~0.4 mJy at 9 GHz.")]
    assert rows[0].flux_density_error is None
