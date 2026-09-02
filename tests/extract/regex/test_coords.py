"""Tests for sexagesimal RA/Dec parser."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from circex.extract.regex.coords import parse_coords


def test_parse_decimal_degrees() -> None:
    result = parse_coords("RA = 191.532, Dec = -23.7534, observed at ...")
    assert result is not None
    ra, dec = result
    assert math.isclose(ra, 191.532, abs_tol=1e-6)
    assert math.isclose(dec, -23.7534, abs_tol=1e-6)


def test_parse_sexagesimal_hms_dms() -> None:
    result = parse_coords("RA = 12h34m56.7s, Dec = -23d45m12.3s")
    assert result is not None
    ra, dec = result
    # 12h 34m 56.7s = 188.7363° ; -23d 45m 12.3s = -23.7534°
    assert math.isclose(ra, 188.7362500, abs_tol=1e-3)
    assert math.isclose(dec, -23.7534166, abs_tol=1e-3)


def test_parse_sexagesimal_colon_notation() -> None:
    result = parse_coords("RA: 12:34:56.7, Dec: -23:45:12.3")
    assert result is not None
    ra, dec = result
    assert math.isclose(ra, 188.7362500, abs_tol=1e-3)
    assert math.isclose(dec, -23.7534166, abs_tol=1e-3)


def test_parse_no_match_returns_none() -> None:
    assert parse_coords("No coordinates here in this prose.") is None


@pytest.mark.parametrize(
    "ra_deg, dec_deg",
    [
        (0.0, 0.0),
        (180.0, 45.0),
        (359.99, -89.99),
        (10.5, -10.5),
    ],
)
def test_decimal_roundtrip(ra_deg: float, dec_deg: float) -> None:
    text = f"RA = {ra_deg:.4f}, Dec = {dec_deg:.4f}"
    result = parse_coords(text)
    assert result is not None
    parsed_ra, parsed_dec = result
    assert math.isclose(parsed_ra, ra_deg, abs_tol=1e-3)
    assert math.isclose(parsed_dec, dec_deg, abs_tol=1e-3)


@given(
    st.floats(min_value=0.001, max_value=359.999, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-89.999, max_value=89.999, allow_nan=False, allow_infinity=False),
)
def test_decimal_property(ra_deg: float, dec_deg: float) -> None:
    text = f"RA = {ra_deg:.6f}, Dec = {dec_deg:.6f}"
    result = parse_coords(text)
    assert result is not None
    parsed_ra, parsed_dec = result
    assert math.isclose(parsed_ra, ra_deg, abs_tol=1e-3)
    assert math.isclose(parsed_dec, dec_deg, abs_tol=1e-3)


def test_combined_label_sexagesimal_with_spaces() -> None:
    """'(RA, Dec) = 14h 57m 49.59s +28d 49m 03.0s' — combined label, spaced (GCN 44827)."""
    text = "discovered OT source at (RA, Dec) = 14h 57m 49.59s +28d 49m 03.0s on 2026-06-04."
    result = parse_coords(text)
    assert result is not None
    ra, dec = result
    assert math.isclose(ra, 224.4566, abs_tol=1e-3)
    assert math.isclose(dec, 28.8175, abs_tol=1e-3)


def test_combined_label_decimal() -> None:
    text = "The position is (RA, Dec) = 224.4566 28.8175 degrees."
    result = parse_coords(text)
    assert result is not None
    ra, dec = result
    assert math.isclose(ra, 224.4566, abs_tol=1e-3)
    assert math.isclose(dec, 28.8175, abs_tol=1e-3)


# SVOM discovery circulars carry the position in two notations, neither of which
# the parser accepted: a combined "R.A., Dec." label with no "=", and a
# split-line "R.A. (J2000) = .." / "Dec. (J2000) = ..". Because the discovery
# circular is where an event's position comes from, missing them cost the whole
# event its source and discarded every follow-up's photometry.
SVOM_45270 = """The localization of the best alert is R.A., Dec. 339.4431, 53.2195 degrees
(J2000) with a 90% confidence level (C.L.) radius of 13.0 arcminutes.

Using onboard processed data we found a new X-ray source located at:
R.A. (J2000) = 22h37m45s
Dec. (J2000) = 53d14m02s
with a 90% C.L. radius of 161 arcseconds.
"""


def test_svom_split_line_sexagesimal():
    ra, dec = parse_coords("R.A. (J2000) = 22h37m45s\nDec. (J2000) = 53d14m02s")
    assert ra == pytest.approx(339.4375, abs=1e-3)
    assert dec == pytest.approx(53.2339, abs=1e-3)


def test_svom_combined_label_without_separator():
    ra, dec = parse_coords("is R.A., Dec. 339.4431, 53.2195 degrees (J2000) with a 90%")
    assert (ra, dec) == pytest.approx((339.4431, 53.2195))


def test_svom_discovery_circular_prefers_the_refined_position():
    """Both notations appear; the refined MXT position is the one to keep."""
    ra, dec = parse_coords(SVOM_45270)
    assert ra == pytest.approx(339.4375, abs=1e-3)
    assert dec == pytest.approx(53.2339, abs=1e-3)


def test_ra_label_does_not_match_mid_word():
    assert parse_coords("The SPECTRA 12.5, Dec. 4.5 were reduced") is None


@pytest.mark.parametrize(
    "text",
    [
        # Swift's boresight in a circular that reports no detection (GCN 21524).
        "The center of the BAT FOV at T0 is RA = 36.075 deg, DEC = -52.287 deg, ROLL = 108.5 deg.",
        # The host, not the burst (GCN 38535).
        "We obtained spectroscopy of this, brighter and more likely host galaxy candidate "
        "(located at RA = 10:21:35.09, Dec = +06:19:45.4) using OSIRIS+.",
        # A foreground galaxy the slit happened to cross (GCN 38877).
        "The slit was aligned in order to cover also the nearby galaxy at coordinates "
        "RA = 13:25:18.72, Dec = +25:37:12.7, with photometric redshift z = 0.2-0.3.",
        # The centre of the imaged field in an upper-limit circular (GCN 36857).
        "We do not detect any new source in our stacked frames having a Field of View (FoV) "
        "of around 13'.0 x 13'.0 centered at R.A. = 23:30:24.55 and Dec. = +01:52:50.9.",
    ],
)
def test_position_of_another_object_is_refused(text: str) -> None:
    assert parse_coords(text) is None


def test_transient_position_survives_a_preceding_fov() -> None:
    # The FoV describes the instrument; the position that follows is still the GRB's.
    text = (
        "The GRB was detected within the extended FoV (about 0.6 deg outside the nominal "
        "18.6deg x 18.6deg FoV) of LEIA, and the on-ground calculated position is "
        "RA=60.6, Dec=-75.4, with an estimated 3-sigma error of 10 arcmin."
    )
    result = parse_coords(text)
    assert result is not None
    assert result[0] == pytest.approx(60.6)
    assert result[1] == pytest.approx(-75.4)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Degree/arcmin/arcsec symbols arrive as U+FFFD (GCN 33429, 21612).
        (
            "RA (J2000): 04h 03m 26.24s\nDec (J2000): -75�� 22��� 43.8�",
            (60.85933, -75.37883),
        ),
        (
            "RA (J2000.0) = 13h 09m 48.27s\nDec (J2000.0) = -23d 23��� 04.3�",
            (197.45112, -23.38453),
        ),
    ],
)
def test_mangled_unit_symbols_keep_full_precision(text: str, expected: tuple[float, float]) -> None:
    result = parse_coords(text)
    assert result is not None
    assert result[0] == pytest.approx(expected[0], abs=1e-4)
    assert result[1] == pytest.approx(expected[1], abs=1e-4)
