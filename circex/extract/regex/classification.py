"""Taxonomy-aware classification matcher.

Walks circex.taxonomy.alias_to_canonical() and scans body text for whole-token
matches against the alias list (longest-alias-first to avoid partial-match
collisions like 'Ia' matching inside 'kilonova').
"""

from __future__ import annotations

import re

from circex.schema import Classification
from circex.taxonomy import alias_to_canonical


def _build_alias_pattern() -> re.Pattern[str]:
    """Build one big alternation regex of all aliases, longest-first."""
    aliases = sorted(alias_to_canonical().keys(), key=len, reverse=True)
    # Escape and anchor to word boundaries. Use case-insensitive matching.
    parts = [re.escape(alias) for alias in aliases]
    pattern = r"\b(?:" + "|".join(parts) + r")\b"
    return re.compile(pattern, re.IGNORECASE)


_ALIAS_PATTERN: re.Pattern[str] | None = None


def _alias_pattern() -> re.Pattern[str]:
    global _ALIAS_PATTERN  # noqa: PLW0603
    if _ALIAS_PATTERN is None:
        _ALIAS_PATTERN = _build_alias_pattern()
    return _ALIAS_PATTERN


def parse_classification(text: str) -> Classification | None:
    """Return the first canonical taxonomy class matched in the text, or None.

    Longest-alias-first ordering means 'Ic-BL' wins over 'Ic' when both could match.
    """
    match = _alias_pattern().search(text)
    if not match:
        return None
    canonical = alias_to_canonical().get(match.group(0).lower())
    if canonical is None:
        return None
    try:
        return Classification(classification=canonical)
    except ValueError:
        return None
