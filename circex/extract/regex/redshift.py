"""Redshift parser: 'z = X.XXX' with optional error + method/type heuristics.

The plan's headline regex is `z\\s*[=~]\\s*(\\d+\\.\\d+)` plus ±200-char context
windows for spec/photo and host/em/abs. We implement both.
"""

from __future__ import annotations

import re

from circex.schema import Redshift, RedshiftMeasure, RedshiftType, Span

_Z_RE = re.compile(
    r"\bz\s*[=~≈]\s*(\d+\.\d+)(?:\s*±\s*(\d+\.\d+))?",
    re.IGNORECASE,
)
_ALT_RE = re.compile(
    r"\b(?:redshift\s+(?:of\s+)?)(\d+\.\d+)",
    re.IGNORECASE,
)
# Bound-redshift phrasings the current Redshift schema cannot represent.
# Examples: "z <= 1.61", "z =< 1.61", "z >= 0.2", "z < 2.5".
# Per docs/labeling_spec.md, when one of these fires the extractor sets
# redshift = None and appends the literal phrase to extraction_meta.notes.
_Z_BOUND_RE = re.compile(
    r"\bz\s*(<=?|>=?|=<|=>|≤|≥)\s*(\d+\.\d+)",
    re.IGNORECASE,
)

# Context-window heuristics. Search ±200 chars around the redshift match.
_CONTEXT_WINDOW = 200

_SPEC_RE = re.compile(r"\bspectroscop(?:ic|y|ically)\b", re.IGNORECASE)
_PHOTO_RE = re.compile(r"\bphotomet(?:ric|ry|rically)\b", re.IGNORECASE)
_HOST_RE = re.compile(r"\bhost(?:\s+galaxy)?\b", re.IGNORECASE)
_EMISSION_RE = re.compile(r"\bemission\s+line", re.IGNORECASE)
_ABSORPTION_RE = re.compile(r"\babsorption\s+line", re.IGNORECASE)


def _classify_measure(context: str) -> RedshiftMeasure | None:
    if _SPEC_RE.search(context):
        return "spectroscopic"
    if _PHOTO_RE.search(context):
        return "photometric"
    return None


def _classify_type(context: str) -> RedshiftType | None:
    if _HOST_RE.search(context):
        return "host"
    if _EMISSION_RE.search(context):
        return "emission"
    if _ABSORPTION_RE.search(context):
        return "absorption"
    return None


def parse_redshift(text: str) -> Redshift | None:
    """Return a Redshift if the text contains z = X.XXX or 'redshift of X.XXX'."""
    result = parse_redshift_with_span(text)
    return result[0] if result is not None else None


def parse_redshift_bound(text: str) -> tuple[str, Span] | None:
    """Return (phrase, Span) for the first bound-redshift mention in `text`, or None.

    Bound redshifts (e.g. "z <= 1.61") cannot be represented in the current
    Redshift point-value schema. The composer in RegexExtractor writes the
    matched phrase to extraction_meta.notes and records a "_redshift_bound"
    provenance key; it does NOT populate Redshift.redshift.
    """
    match = _Z_BOUND_RE.search(text)
    if not match:
        return None
    phrase = match.group(0)
    span = Span(start=match.start(), end=match.end(), snippet=phrase)
    return phrase, span


def parse_redshift_with_span(text: str) -> tuple[Redshift, Span] | None:
    """Same as parse_redshift, but also return a Span pointing at the z-match."""
    match = _Z_RE.search(text) or _ALT_RE.search(text)
    if not match:
        return None

    z = float(match.group(1))
    err: float | None = None
    if _Z_RE.match(match.group(0)) is not None:
        try:
            err_str = match.group(2)
        except IndexError:
            err_str = None
        if err_str:
            err = float(err_str)

    ctx_start = max(0, match.start() - _CONTEXT_WINDOW)
    ctx_end = min(len(text), match.end() + _CONTEXT_WINDOW)
    context = text[ctx_start:ctx_end]

    redshift = Redshift(
        redshift=z,
        redshift_error=err,
        redshift_measure=_classify_measure(context),
        redshift_type=_classify_type(context),
    )
    span = Span(start=match.start(), end=match.end(), snippet=match.group(0))
    return redshift, span
