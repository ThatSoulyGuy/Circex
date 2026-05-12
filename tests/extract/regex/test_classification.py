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
