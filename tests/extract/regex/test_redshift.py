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
