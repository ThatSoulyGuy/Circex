"""Tests for the extended event patterns + GCN cross-ref extractor."""

from __future__ import annotations

from circex.extract.regex.regex_events import extract_gcn_xrefs, extract_matches


def test_extract_tns_at_designation() -> None:
    assert "AT2017GFO" in extract_matches("Counterpart AT2017gfo to GW170817.")


def test_extract_tns_sn_designation() -> None:
    assert "SN2024GHI" in extract_matches("Classification: SN 2024ghi (Type Ia).")


def test_extract_old_style_sn() -> None:
    assert "SN1987A" in extract_matches("SN 1987A in the LMC.")


def test_extract_ztf_designation() -> None:
    assert "ZTF21AAQKQFP" in extract_matches("Source ZTF21aaqkqfp detected.")


def test_extract_atlas_designation() -> None:
    matches = extract_matches("ATLAS24abc photometry.")
    assert any("ATLAS24" in m for m in matches)


def test_extract_asassn_designation() -> None:
    assert "ASASSN-19A" in extract_matches("ASASSN-19a brightened.") or \
           any("ASASSN" in m for m in extract_matches("ASASSN-19a brightened."))


def test_extract_panstarrs_designation() -> None:
    assert "PS22GGN" in extract_matches("PS22ggn rises.")


def test_extract_goto_designation() -> None:
    matches = extract_matches("GOTO 24abc shows...")
    assert any("GOTO" in m for m in matches)


# ---- gravitational-wave designations (P2 #8) ----


def test_extract_gw_designation() -> None:
    assert "GW170817" in extract_matches("Counterpart to GW170817 confirmed.")


def test_extract_gw_with_subevent_suffix() -> None:
    assert "GW190425" in extract_matches("GW190425 localization updated.")


def test_extract_gw_and_at_together() -> None:
    """The multimessenger case: both names recovered, AT name not dropped."""
    matches = extract_matches("Optical counterpart AT2017gfo to GW170817.")
    assert "GW170817" in matches
    assert "AT2017GFO" in matches


# ---- GCN cross-refs ----


def test_gcn_xref_hash_form() -> None:
    assert extract_gcn_xrefs("see GCN #12345 and GCN Circular #67890") == [12345, 67890]


def test_gcn_xref_word_form() -> None:
    assert extract_gcn_xrefs("Reported in GCN Circ. 9999.") == [9999]


def test_gcn_xref_deduplicates() -> None:
    text = "First mentioned in GCN #205, see also GCN Circular 205, and GCN #213."
    assert extract_gcn_xrefs(text) == [205, 213]


def test_gcn_xref_no_match() -> None:
    assert extract_gcn_xrefs("No references here.") == []
