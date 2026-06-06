"""Tests for circex.taxonomy — YAML loader + alias map."""

from __future__ import annotations

from circex.taxonomy import (
    alias_to_canonical,
    canonical_classes,
    class_to_path,
    get_taxonomy,
    normalize_classification,
    taxonomy_path,
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


# ---- taxonomy_path (P2 #9) ----


def test_taxonomy_path_root_to_leaf() -> None:
    path = taxonomy_path("Ia")
    assert path is not None
    assert path[0] == "Time-domain Source"
    assert path[-1] == "Ia"
    # Each canonical class on the path is itself a canonical class.
    assert "Supernova" in path


def test_taxonomy_path_unknown_class_is_none() -> None:
    assert taxonomy_path("not a real class") is None


def test_taxonomy_path_every_canonical_class_has_a_path() -> None:
    """class_to_path must cover the full canonical set (no orphans)."""
    paths = class_to_path()
    for cls in canonical_classes():
        assert cls in paths, f"{cls!r} has no taxonomy path"
        assert paths[cls][-1] == cls


def test_taxonomy_path_returns_a_copy() -> None:
    """Callers must not be able to mutate the cached path in place."""
    p1 = taxonomy_path("Ia")
    assert p1 is not None
    p1.append("MUTATED")
    p2 = taxonomy_path("Ia")
    assert p2 is not None and "MUTATED" not in p2
