"""Tests for the magnitude parsers (single + table)."""

from __future__ import annotations

from circex.extract.regex.mag_table import (
    infer_bandpass,
    infer_mag_system,
    parse_mag_table,
    parse_single_mags,
)


def test_infer_sloan_is_ab() -> None:
    assert infer_mag_system("r") == "AB"
    assert infer_mag_system("g") == "AB"
    assert infer_mag_system("z") == "AB"


def test_infer_bessel_is_vega() -> None:
    assert infer_mag_system("R") == "Vega"
    assert infer_mag_system("V") == "Vega"


def test_infer_nir_is_vega() -> None:
    assert infer_mag_system("J") == "Vega"
    assert infer_mag_system("Ks") == "Vega"


def test_parse_single_detection_with_error() -> None:
    rows = parse_single_mags("The OT is detected at r = 18.42 ± 0.05 mag.")
    assert any(p.filter == "r" and p.mag == 18.42 and p.mag_error == 0.05 for p in rows)


def test_parse_single_upper_limit() -> None:
    rows = parse_single_mags("3-sigma upper limit r > 22.5 in the field.")
    matches = [p for p in rows if p.filter == "r" and p.limiting_mag == 22.5]
    assert len(matches) == 1


def test_rejects_redshift_value_as_z_mag() -> None:
    """'z = 1.61' is a redshift, not a Sloan-z mag; must NOT be returned."""
    rows = parse_single_mags("Redshift z = 1.61 from absorption lines.")
    assert not any(p.filter == "z" and p.mag == 1.61 for p in rows)


def test_rejects_too_bright_mag() -> None:
    """Magnitudes below 5 are vanishingly rare in optical circulars; reject."""
    rows = parse_single_mags("Some random equation r = 3.14 in cosmology.")
    assert not any(p.filter == "r" and p.mag == 3.14 for p in rows)


def test_parse_clean_table() -> None:
    text = """
Date          Filter   Mag      Err
2020-01-01    r        18.42    0.05
2020-01-02    r        18.51    0.05
2020-01-03    g        19.10    0.07
""".strip()
    rows = parse_mag_table(text)
    assert len(rows) == 3
    assert {(p.filter, p.mag) for p in rows} == {
        ("r", 18.42), ("r", 18.51), ("g", 19.10),
    }


def test_table_trailing_error_column_is_captured() -> None:
    """Regression: the last column ('Err') was dropped because the header line
    kept its trailing newline, so 'Err\\n' failed keyword classification."""
    text = "Date          Filter   Mag      Err\n2020-01-01    r        18.42    0.05"
    rows = parse_mag_table(text)
    assert len(rows) == 1
    assert rows[0].mag == 18.42
    assert rows[0].mag_error == 0.05  # must not be None


def test_parse_empty_when_no_table() -> None:
    """Prose-only circulars should produce zero table rows (the PDF's expected failure mode)."""
    text = (
        "We observed the field with the GTC. The optical transient appears to have "
        "faded over the past 24 hours, consistent with previous reports."
    )
    assert parse_mag_table(text) == []


# ---- bandpass crosswalk (P1 #4) ----


def test_infer_bandpass_sloan() -> None:
    assert infer_bandpass("u") == "sdssu"
    assert infer_bandpass("g") == "sdssg"
    assert infer_bandpass("r") == "sdssr"
    assert infer_bandpass("i") == "sdssi"
    assert infer_bandpass("z") == "sdssz"


def test_infer_bandpass_y_is_panstarrs() -> None:
    assert infer_bandpass("y") == "ps1::y"


def test_infer_bandpass_bessel() -> None:
    assert infer_bandpass("U") == "bessellu"
    assert infer_bandpass("B") == "bessellb"
    assert infer_bandpass("V") == "bessellv"
    assert infer_bandpass("R") == "bessellr"
    assert infer_bandpass("I") == "besselli"


def test_infer_bandpass_nir() -> None:
    assert infer_bandpass("J") == "2massj"
    assert infer_bandpass("H") == "2massh"
    assert infer_bandpass("K") == "2massks"
    assert infer_bandpass("Ks") == "2massks"


def test_infer_bandpass_unfiltered_is_none() -> None:
    assert infer_bandpass("clear") is None
    assert infer_bandpass("C") is None


def test_single_mag_populates_bandpass() -> None:
    rows = parse_single_mags("The OT is at r = 18.42 ± 0.05 mag.")
    r_rows = [p for p in rows if p.filter == "r"]
    assert r_rows and r_rows[0].bandpass == "sdssr"
    # Raw filter token always retained.
    assert r_rows[0].filter == "r"


def test_table_rows_populate_bandpass() -> None:
    text = """
Date          Filter   Mag      Err
2020-01-01    r        18.42    0.05
2020-01-02    g        19.10    0.07
""".strip()
    rows = parse_mag_table(text)
    by_filter = {p.filter: p.bandpass for p in rows}
    assert by_filter == {"r": "sdssr", "g": "sdssg"}


# ---- space-separated detection (fixed-width tables / terse prose; GRB 260604C flurry) ----


def test_spaced_detection_with_cousins_filter() -> None:
    """The seed-circular row format: 'Rc  23.08 +/- 0.18' (no '=', Cousins R)."""
    rows = parse_single_mags("2026.06.08 20:01:14 4.01102 12*300 Rc     23.08 +/- 0.18  23.8")
    det = [p for p in rows if p.mag == 23.08]
    assert det, "the space-separated detection should be recovered"
    p = det[0]
    assert p.filter == "R" and p.mag_error == 0.18
    assert p.bandpass == "bessellr" and p.mag_system == "Vega"
    assert p.is_detection is True


def test_spaced_detection_unicode_pm() -> None:
    rows = parse_single_mags("r 19.5 ± 0.05 in good conditions")
    assert any(p.filter == "r" and p.mag == 19.5 and p.mag_error == 0.05 for p in rows)


def test_spaced_detection_requires_error_term() -> None:
    """No +/- after the mag -> not a detection (precision guard)."""
    assert parse_single_mags("We obtained 12 x 300 sec images of the field.") == []
    assert not any(p.mag == 300 for p in parse_single_mags("exposure r 300 sec"))


def test_spaced_form_does_not_double_count_equals_form() -> None:
    """'r = 18.42 ± 0.05' is matched once, not by both the '=' and spaced forms."""
    rows = [p for p in parse_single_mags("r = 18.42 ± 0.05") if p.mag == 18.42]
    assert len(rows) == 1


def test_spaced_detection_rejects_redshift_as_z_mag() -> None:
    """'z 0.215 +/- 0.001' is a redshift, not a Sloan-z mag (z<10 guard)."""
    assert not any(p.filter == "z" for p in parse_single_mags("z 0.215 +/- 0.001"))
