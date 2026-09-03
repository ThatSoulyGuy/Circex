"""Builds the telescope/bandpass -> instrument_id maps from a SkyPortal instance.

Hand-maintained maps drift from the instance they describe, so both are derived
from what it actually has. Where a name does not identify one instrument the
entry is left out rather than guessed: an unroutable row falls back to the
configured default, which is visible, while a wrong instrument is not.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _telescope_keys(record: dict[str, Any]) -> list[str]:
    """The names a circular might use for this instrument's telescope."""
    telescope = record.get("telescope") or {}
    return [str(v).strip() for v in (telescope.get("nickname"), telescope.get("name")) if v]


def derive_instrument_map(instruments: list[dict[str, Any]]) -> dict[str, int]:
    """Telescope name -> instrument_id, for telescopes hosting one instrument."""
    by_key: dict[str, set[int]] = defaultdict(set)
    for record in instruments:
        instrument_id = record.get("id")
        if instrument_id is None:
            continue
        for key in _telescope_keys(record):
            by_key[key].add(int(instrument_id))
    return {key: ids.pop() for key, ids in by_key.items() if len(ids) == 1}


def derive_bandpass_instrument_map(instruments: list[dict[str, Any]]) -> dict[str, int]:
    """Bandpass -> instrument_id, for bandpasses only one instrument declares.

    A mission band names its instrument exactly (epfxt is EP/FXT); an optical one
    does not (dozens of instruments carry sdssr), so only the unique ones map.
    """
    by_band: dict[str, set[int]] = defaultdict(set)
    for record in instruments:
        instrument_id = record.get("id")
        if instrument_id is None:
            continue
        for band in record.get("filters") or []:
            by_band[str(band)].add(int(instrument_id))
    return {band: ids.pop() for band, ids in by_band.items() if len(ids) == 1}
