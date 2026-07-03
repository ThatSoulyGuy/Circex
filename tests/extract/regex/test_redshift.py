"""Tests for the redshift parser."""

from __future__ import annotations

from circex.extract.regex.redshift import parse_redshift


def test_parse_simple_z() -> None:
    r = parse_redshift("Measurement yields z = 0.954 from spectroscopy.")
    assert r is not None
    assert r.redshift == 0.954
    assert r.redshift_measure == "spectroscopic"


def test_parse_z_with_error() -> None:
    r = parse_redshift("Spectroscopy gives z = 1.234 ± 0.005.")
    assert r is not None
    assert r.redshift == 1.234
    assert r.redshift_error == 0.005


def test_parse_redshift_of_phrase() -> None:
    r = parse_redshift("The team reports a redshift of 2.5 for the source.")
    assert r is not None
    assert r.redshift == 2.5


def test_classify_host_galaxy() -> None:
    r = parse_redshift("Host galaxy spectrum gives z = 0.198.")
    assert r is not None
    assert r.redshift_type == "host"


def test_classify_emission_lines() -> None:
    r = parse_redshift("Detected strong emission lines at z = 0.5.")
    assert r is not None
    assert r.redshift_type == "emission"


def test_classify_absorption_lines() -> None:
    r = parse_redshift("Absorption lines yield z = 3.21 in the spectrum.")
    assert r is not None
    assert r.redshift_type == "absorption"


def test_classify_photometric() -> None:
    r = parse_redshift("Photometric redshift estimate gives z = 0.42.")
    assert r is not None
    assert r.redshift_measure == "photometric"


def test_no_match() -> None:
    assert parse_redshift("This circular has no redshift information.") is None


# ---- bound redshifts (P2 #11) ----


def test_parse_redshift_bound_upper() -> None:
    from circex.extract.regex.redshift import parse_redshift_bound

    result = parse_redshift_bound("Lower limit z <= 1.61 from absorption.")
    assert result is not None
    phrase, span = result
    assert phrase == "z <= 1.61"
    assert "1.61" in span.snippet


def test_parse_redshift_bound_lower() -> None:
    from circex.extract.regex.redshift import parse_redshift_bound

    result = parse_redshift_bound("Constraint: z >= 0.2 for the host.")
    assert result is not None
    phrase, _ = result
    assert phrase == "z >= 0.2"


def test_parse_redshift_bound_legacy_notation() -> None:
    """Old-style '=<' shows up in 1990s circulars (e.g. GRB 990123)."""
    from circex.extract.regex.redshift import parse_redshift_bound

    result = parse_redshift_bound("redshift z =< 1.61 (Kelson et al.)")
    assert result is not None
    phrase, _ = result
    assert phrase == "z =< 1.61"


def test_parse_redshift_bound_does_not_match_point_value() -> None:
    from circex.extract.regex.redshift import parse_redshift_bound

    assert parse_redshift_bound("z = 0.215 +/- 0.001") is None


def test_skips_nearby_unassociated_galaxy_photoz() -> None:
    """A nearby galaxy's photo-z, explicitly disclaimed, must NOT be extracted (GCN 44834)."""
    text = (
        "We notice the presence of a red galaxy with a photo-z = 0.343 +/- 0.031 "
        '(DESI Legacy Survey) at 18.9" from the optical counterpart position. This '
        "corresponds to a Pcc ~ 0.16, which makes an association very unlikely."
    )
    assert parse_redshift(text) is None


def test_still_extracts_source_photoz() -> None:
    """A photometric redshift OF the transient (no offset/association caveat) still parses."""
    r = parse_redshift("The afterglow colours imply a photometric redshift z = 0.5.")
    assert r is not None
    assert r.redshift == 0.5


def test_zband_magnitude_is_not_a_redshift() -> None:
    """'z = 19.21 +/- 0.06' is a Sloan z-band magnitude, not a redshift (GCN 44834)."""
    assert parse_redshift("z = 19.21 +/- 0.06") is None


def test_high_but_plausible_redshift_still_parses() -> None:
    r = parse_redshift("The GRB is at a spectroscopic z = 8.2.")
    assert r is not None and r.redshift == 8.2
