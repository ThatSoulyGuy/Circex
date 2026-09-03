"""Telescope / instrument name canonicalization.

Reads the seed alias map shipped in `telescope_aliases.yaml` (package data) and
exposes case-insensitive canonicalizers. Unknown-but-non-null inputs return
None — callers keep the raw string and treat a null canonical as "saw something
we couldn't normalize". The map is a seed; extend it from ICARE's instrument_id
table.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import cast

import yaml

_ALIASES_PATH = Path(__file__).parent / "telescope_aliases.yaml"


def _build_map(section: dict[str, list[str]]) -> dict[str, str]:
    """Lowercased-alias -> canonical. Canonical also maps to itself; first wins."""
    out: dict[str, str] = {}
    for canonical, aliases in section.items():
        out.setdefault(canonical.strip().lower(), canonical)
        for alias in aliases or []:
            out.setdefault(str(alias).strip().lower(), canonical)
    return out


@cache
def _alias_maps() -> tuple[dict[str, str], dict[str, str]]:
    data = cast(dict[str, dict[str, list[str]]], yaml.safe_load(_ALIASES_PATH.read_text("utf-8")))
    telescopes = _build_map(data.get("telescopes", {}))
    instruments = _build_map(data.get("instruments", {}))
    return telescopes, instruments


def canonicalize_telescope(name: str | None) -> str | None:
    """Return the canonical telescope name for `name`, or None if unknown/empty."""
    if not name:
        return None
    return _alias_maps()[0].get(name.strip().lower())


def canonicalize_instrument(name: str | None) -> str | None:
    """Return the canonical instrument name for `name`, or None if unknown/empty."""
    if not name:
        return None
    return _alias_maps()[1].get(name.strip().lower())


@cache
def _alias_source() -> dict[str, dict[str, list[str]]]:
    """The alias map as written, keeping the original spellings."""
    return cast(
        dict[str, dict[str, list[str]]],
        yaml.safe_load(_ALIASES_PATH.read_text("utf-8")),
    )
