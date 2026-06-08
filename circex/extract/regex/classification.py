"""Taxonomy-aware classification matcher.

Walks circex.taxonomy.alias_to_canonical() and scans body text for whole-token
matches against the alias list (longest-alias-first to avoid partial-match
collisions like 'Ia' matching inside 'kilonova').

Short aliases are the dominant false-positive source: the taxonomy includes
single- and two-letter aliases (e.g. 'O' for Overtone, 'M' for Mira) that match
author initials and stray substrings. The GRB 260604C flurry test produced ~9
garbage classifications out of 12 this way (see docs/flurry_test_grb260604c.md).
We guard against it with two rules:

  - 1-character aliases are dropped entirely (they never carry classification
    signal in prose and reliably match author initials).
  - 2-character aliases (e.g. 'Ia', 'Ib', 'Ic', 'II') only match when a
    classification-context cue ('type', 'classified', 'spectrum', 'supernova',
    'consistent with', ...) appears within a small window — which preserves
    'Type Ia' while rejecting 'in' (Orion) and 'Fu' (FU Ori) in GRB prose.

Aliases of 3+ characters match directly, as before.
"""

from __future__ import annotations

import re

from circex.schema import Classification, Span
from circex.taxonomy import alias_to_canonical

# Aliases this short or shorter are ambiguous; see module docstring.
_SHORT_ALIAS_MAX = 2
# Window (chars on each side) to look for a classification cue near a 2-char alias.
_CONTEXT_WINDOW = 60

# Classification-action cues. Deliberately excludes bare "SN" (appears in every
# SN designation) to avoid re-admitting the false positives this guard removes.
_CLASS_CONTEXT = re.compile(
    r"\b(?:typ(?:e|ed|ing)|classif\w*|spectrum|spectra|spectroscop\w*|"
    r"supernova|consistent\s+with|identif\w*|resembl\w*|template|best[-\s]?fit)\b",
    re.IGNORECASE,
)


def _build_alias_pattern() -> re.Pattern[str]:
    """Build one big alternation regex of all aliases >1 char, longest-first."""
    aliases = sorted(
        (a for a in alias_to_canonical() if len(a) > 1), key=len, reverse=True
    )
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
    result = parse_classification_with_span(text)
    return result[0] if result is not None else None


def parse_classification_with_span(
    text: str,
) -> tuple[Classification, Span] | None:
    """Same as parse_classification, plus a Span pointing at the alias match.

    Returns the first *accepted* match: short (<=2 char) aliases are only
    accepted with a nearby classification cue, so a stray author initial or
    substring is skipped rather than misclassifying the circular.
    """
    for match in _alias_pattern().finditer(text):
        token = match.group(0)
        canonical = alias_to_canonical().get(token.lower())
        if canonical is None:
            continue
        if len(token) <= _SHORT_ALIAS_MAX:
            window = text[
                max(0, match.start() - _CONTEXT_WINDOW) : match.end() + _CONTEXT_WINDOW
            ]
            if not _CLASS_CONTEXT.search(window):
                continue
        try:
            cls = Classification(classification=canonical)
        except ValueError:
            continue
        span = Span(start=match.start(), end=match.end(), snippet=token)
        return cls, span
    return None
