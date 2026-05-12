"""Tests for circex.taxonomy — YAML loader + alias map."""

from __future__ import annotations

from circex.taxonomy import (
    alias_to_canonical,
    canonical_classes,
    get_taxonomy,
    normalize_classification,
)


def test_taxonomy_loads() -> None:
    tx = get_taxonomy()
    assert isinstance(tx, dict)
    assert "class" in tx
    assert tx["class"] == "Time-domain Source"


def test_canonical_classes_nonempty() -> None:
    classes = canonical_classes()
    assert "Ia" in classes
    assert "Ib" in classes
    assert "Ic" in classes
    assert "Ic-BL" in classes
    # 100+ canonical classes expected
    assert len(classes) > 100


def test_alias_to_canonical_maps_known_aliases() -> None:
    m = alias_to_canonical()
    # "SNIa" is an explicit alias in supernovae.yaml.
    assert m["snia"] == "Ia"
    # "SN Ic" should map to Ic.
    assert m["sn ic"] == "Ic"
    # Canonical names map to themselves (case-insensitive).
    assert m["ia"] == "Ia"


def test_normalize_classification_returns_canonical() -> None:
    assert normalize_classification("SNIa") == "Ia"
    assert normalize_classification("  sn ic  ") == "Ic"
    assert normalize_classification("not a real class name") is None
