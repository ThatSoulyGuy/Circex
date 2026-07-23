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
        ("r", 18.42),
        ("r", 18.51),
        ("g", 19.10),
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


def test_slashed_plus_minus_error_is_parsed() -> None:
    """'g = 19.69 +/- 0.04' — the +/- error form must populate mag_error (GCN 44834)."""
    from circex.extract.regex.mag_table import parse_single_mags

    rows = parse_single_mags("We detected the counterpart at g = 19.69 +/- 0.04.")
    assert len(rows) == 1
    assert rows[0].mag == 19.69
    assert rows[0].mag_error == 0.04


def test_excludes_nearby_galaxy_photometry() -> None:
    """A nearby galaxy's magnitudes must NOT be extracted as transient photometry (GCN 44834)."""
    from circex.extract.regex.mag_table import parse_single_mags

    text = (
        "The counterpart is at r = 19.56 +/- 0.03. We also notice a red galaxy with "
        "g = 21.69 +/- 0.02, r = 20.15 +/- 0.01, z = 19.10 +/- 0.01 at 18.9 arcsec offset."
    )
    rows = parse_single_mags(text)
    mags = sorted(p.mag for p in rows if p.mag is not None)
    assert mags == [19.56]  # only the transient's r-band, none of the galaxy's


def test_reference_star_photometry_excluded() -> None:
    from circex.extract.regex.mag_table import parse_single_mags

    rows = parse_single_mags("OT at R = 20.1 +/- 0.1. The comparison star has R = 15.3 +/- 0.02.")
    assert sorted(p.mag for p in rows if p.mag is not None) == [20.1]


# ---- pipe-delimited (markdown) tables ----


def test_pipe_table_relative_time_with_trigger() -> None:
    """'| Tmid-TGRB (hrs) | Filter | Magnitude |' resolves rows against T0 (GCN 44835)."""
    from datetime import UTC, datetime

    from circex.extract.regex.mag_table import parse_pipe_table_with_spans

    text = (
        "| Tmid-TGRB (hrs) | Filter    | Magnitude      |\n"
        "| --------------- | --------- | -------------- |\n"
        "| 1.47            | Rc (Vega) | 17.43 +/- 0.03 |\n"
        "| 3.17            | r (AB)    | 18.41 +/- 0.05 |\n"
    )
    t0 = datetime(2026, 6, 4, 20, 20, tzinfo=UTC)
    rows = [r for r, _ in parse_pipe_table_with_spans(text, t0)]
    assert len(rows) == 2
    assert rows[0].bandpass == "bessellr" and rows[0].mag == 17.43 and rows[0].mag_error == 0.03
    assert rows[0].obs_mjd is not None
    assert rows[1].bandpass == "sdssr"


def test_pipe_table_two_column_with_limit() -> None:
    """'Filter | Mag (AB)' (single pipe) with '(Magnitude limit: X)' (GCN 44857)."""
    from circex.extract.regex.mag_table import parse_pipe_table_with_spans

    text = (
        "Filter | Mag (AB)\n"
        "     g | 22.0938 ± 0.0008 (Magnitude limit: 24.6925)\n"
        "     r | 21.7162 ± 0.0005 (Magnitude limit: 23.9245)\n"
    )
    rows = [r for r, _ in parse_pipe_table_with_spans(text)]
    assert len(rows) == 2
    assert rows[0].filter == "g" and rows[0].bandpass == "sdssg"
    assert rows[0].mag == 22.0938 and rows[0].limiting_mag == 24.6925
    assert rows[0].obs_mjd is None  # time is in prose, resolved separately


def test_pipe_table_absolute_time_column() -> None:
    from circex.extract.regex.mag_table import parse_pipe_table_with_spans

    text = (
        "| mid-time(UT)        | Filter | ABmag        |\n"
        "| 2026-06-04 23:46:15 | r      | 18.45 ± 0.04 |\n"
    )
    rows = [r for r, _ in parse_pipe_table_with_spans(text)]
    assert len(rows) == 1 and rows[0].mag == 18.45 and rows[0].obs_mjd is not None


def test_pipe_table_unmappable_filter_skipped() -> None:
    """Clear/unfiltered rows (no canonical bandpass) are not emitted."""
    from circex.extract.regex.mag_table import parse_pipe_table_with_spans

    text = "| Tmid-T0 (h) | Mag (AB) |\n| 0.33 | 16.42 +/- 0.02 |\n"
    assert parse_pipe_table_with_spans(text) == []  # no filter column -> nothing postable


# ---- fixed-width SAO-RAS / IKI template ----


def test_fixed_width_saoras_template_plus_minus() -> None:
    """'2026.06.08 20:01:14 ... Rc 23.08 +/- 0.18 23.8' (GCN 44877): dotted date, +/-, UL."""
    from circex.extract.regex.mag_table import parse_fixed_width_table_with_spans

    text = (
        "Date       UTstart  t-T0    Exp.   Filter Mag +/- Err.    UL\n"
        "                    (mid,d) (n*s)                         (3-sigma)\n"
        "2026.06.08 20:01:14 4.01102 12*300 Rc     23.08 +/- 0.18  23.8\n"
    )
    rows = [r for r, _ in parse_fixed_width_table_with_spans(text)]
    assert len(rows) == 1
    r = rows[0]
    assert r.bandpass == "bessellr" and r.mag == 23.08 and r.mag_error == 0.18
    assert r.limiting_mag == 23.8
    assert r.obs_mjd is not None and abs(r.obs_mjd - 61199.834) < 0.01


def test_fixed_width_space_separated_err_and_dash_date() -> None:
    """'2026-06-05 21:31:13 ... R 21.35 0.14 22.4' (GCN 44858): dash date, no +/-, 2 rows."""
    from circex.extract.regex.mag_table import parse_fixed_width_table_with_spans

    text = (
        "Date       UTstart  t-T0    Exp.   Filter Mag    Err.    UL\n"
        "                    (mid,d) (n*s)                      (3-sigma)\n"
        "2026-06-05 21:31:13 1.07291 26x150 R      21.35  0.14   22.4\n"
        "2026-06-06 20:09:21 2.03341 46x150 R      21.53  0.19   22.3\n"
    )
    rows = [r for r, _ in parse_fixed_width_table_with_spans(text)]
    assert len(rows) == 2
    assert rows[0].mag == 21.35 and rows[0].mag_error == 0.14 and rows[0].limiting_mag == 22.4
    assert rows[1].mag == 21.53 and rows[1].obs_mjd is not None


def test_fixed_width_ignores_loose_generic_table() -> None:
    """A loose table (no exp/utstart header, minute-precision time) is left to parse_mag_table."""
    from circex.extract.regex.mag_table import parse_fixed_width_table_with_spans

    text = "Date              Filter  Mag     Err\n2024-01-02 04:30  r       20.42   0.05\n"
    assert parse_fixed_width_table_with_spans(text) == []


# ---- ZTF/GROWTH boxed candidate table (GCN 45198 template) ----

_ZTF_TABLE = """\
We are left with the following high-significance transient candidate by our
pipeline, lying within the 90.0% localization of the skymap.

+--------------------------------------------------------------------------------+
| ZTF Name     | IAU Name  | RA (deg)    | DEC (deg)   | Filter | Mag   | MagErr |
+--------------------------------------------------------------------------------+
| ZTF26abjbxfs |  AT 2026vts  | 191.3022538 | +30.5970446 | r      | 19.78 | 0.07   |
+--------------------------------------------------------------------------------+
"""


def test_pipe_table_reads_boxed_ztf_template() -> None:
    """+---+ frame lines must not end the row scan; MagErr is its own column."""
    from circex.extract.regex.mag_table import parse_pipe_table_with_spans

    rows = parse_pipe_table_with_spans(_ZTF_TABLE)
    assert len(rows) == 1
    row, span = rows[0]
    assert row.filter == "r"
    assert row.mag == 19.78
    assert row.mag_error == 0.07  # from the MagErr column, not the Mag cell
    assert "ZTF26abjbxfs" in span.snippet


def test_pipe_candidate_extracts_names_and_decimal_coords() -> None:
    from circex.extract.regex.mag_table import parse_pipe_candidate_with_span

    hit = parse_pipe_candidate_with_span(_ZTF_TABLE)
    assert hit is not None
    names, ra, dec, span = hit
    assert names == ["ZTF26abjbxfs", "AT 2026vts"]
    assert ra == 191.3022538
    assert dec == 30.5970446
    assert "191.3022538" in span.snippet


def test_pipe_candidate_refuses_multi_row_survey_lists() -> None:
    """Two candidates = a survey product, not a claimed counterpart (spec rule)."""
    from circex.extract.regex.mag_table import parse_pipe_candidate_with_span

    multi = (
        _ZTF_TABLE.replace(
            "+--------------------------------------------------------------------------------+\n",
            "",
        )
        + "| ZTF26xxyyzzq |  AT 2026abc  | 12.5000000 | -4.1000000 | g      | 20.10 | 0.10   |\n"
    )
    assert parse_pipe_candidate_with_span(multi) is None
