"""Tests for circex.data.telescopes — alias canonicalization (P1 #5)."""

from __future__ import annotations

from circex.data.telescopes import canonicalize_instrument, canonicalize_telescope


def test_telescope_alias_maps_to_canonical() -> None:
    assert canonicalize_telescope("the VLT") == "VLT"
    assert canonicalize_telescope("ESO-VLT") == "VLT"
    assert canonicalize_telescope("Pan-STARRS1") == "Pan-STARRS"


def test_telescope_canonical_maps_to_itself() -> None:
    assert canonicalize_telescope("VLT") == "VLT"


def test_telescope_case_and_whitespace_insensitive() -> None:
    assert canonicalize_telescope("  vlt  ") == "VLT"


def test_telescope_unknown_is_none() -> None:
    assert canonicalize_telescope("Backyard 8-inch") is None


def test_telescope_empty_is_none() -> None:
    assert canonicalize_telescope(None) is None
    assert canonicalize_telescope("") is None


def test_svom_vt_alias() -> None:
    """ICARE example: 'VT' and 'SVOM/VT' both map to one canonical."""
    assert canonicalize_telescope("VT") == canonicalize_telescope("SVOM/VT")


def test_instrument_alias_maps_to_canonical() -> None:
    assert canonicalize_instrument("VLT/X-shooter") == "X-shooter"
    assert canonicalize_instrument("XSHOOTER") == "X-shooter"
    assert canonicalize_instrument("GTC/OSIRIS") == "OSIRIS"


def test_instrument_unknown_is_none() -> None:
    assert canonicalize_instrument("HomebrewSpectrograph") is None
