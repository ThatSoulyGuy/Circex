"""Tests for the taxonomy-aware classification matcher."""

from __future__ import annotations

from circex.extract.regex.classification import parse_classification


def test_match_canonical_class() -> None:
    c = parse_classification("Spectroscopic typing confirms Ia.")
    assert c is not None and c.classification == "Ia"


def test_match_via_alias() -> None:
    # 'SNIa' is an alias for 'Ia' in supernovae.yaml.
    c = parse_classification("Classified as SNIa from absorption lines.")
    assert c is not None
    assert c.classification == "Ia"


def test_match_longer_alias_wins_at_position() -> None:
    # If both 'Ic' and 'Ic-BL' could match at the same position, the longer alias wins.
    c = parse_classification("This is an Ic-BL with broad lines.")
    assert c is not None
    assert c.classification == "Ic-BL"


def test_no_match_when_no_taxonomy_word() -> None:
    assert parse_classification("Just plain text with no class names.") is None


def test_match_tde_alias() -> None:
    c = parse_classification("Likely a TDE based on the X-ray follow-up.")
    assert c is not None
    # 'TDE' is the alias; canonical is 'Tidal Disruption Event'.
    assert c.classification == "Tidal Disruption Event"


# ---- short-alias false-positive guard (GRB 260604C flurry; docs/flurry_test_grb260604c.md) ----


def test_author_initial_is_not_a_classification() -> None:
    """1-char aliases are dropped: 'O.' (O. Spiridonova) must not become 'Overtone'."""
    assert parse_classification("A. Moskvitin, O. Spiridonova report observations.") is None


def test_substring_two_char_alias_without_context_rejected() -> None:
    """'in' (an Orion alias) in plain prose, no classification cue -> not Orion.

    (The sentence avoids other taxonomy words; we assert the specific
    false-positive the guard targets does not occur.)"""
    c = parse_classification("The optical counterpart brightened in our latest frames.")
    assert c is None or c.classification != "Orion"


def test_two_char_alias_initial_rejected() -> None:
    """'Fu' (FU Ori alias) as a name fragment, no cue -> no match."""
    assert parse_classification("Observations reported by Fu et al. last night.") is None


def test_two_char_alias_with_context_accepted() -> None:
    """A real 2-char class with a classification cue is still matched."""
    c = parse_classification("The spectrum is consistent with a Type Ia event.")
    assert c is not None and c.classification == "Ia"


def test_bare_two_char_alias_without_context_rejected() -> None:
    assert parse_classification("the transient is Ia") is None
