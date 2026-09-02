"""Date / time parsers: UTC, MJD, and literal T+offset captures.

Per PDF decision 4, T+offset captures are stored as TimeOffset records literally —
no resolution against T0 in v1.
"""

from __future__ import annotations

import re

from circex.schema import Span, TimeOffset, TimeOffsetUnit

# T+234s, T+8.5h, T+12 d, T-300 s, T + 4 hours
_T_OFFSET_RE = re.compile(
    r"""
    \bT
    \s*(?P<sign>[+\-−–])\s*
    (?P<value>\d+(?:\.\d+)?)
    \s*
    (?P<unit>s(?:ec(?:ond)?s?)?|m(?:in(?:ute)?s?)?|h(?:our)?s?|d(?:ay)?s?)
    \b
    """,
    re.VERBOSE | re.IGNORECASE,
)

# "approximately X hours after the trigger", "X minutes post-burst", "5.9d after
# the Swift/BAT trigger". Circulars say "burst" as often as "trigger", and name
# the instrument in between, so both are accepted.
_POST_TRIGGER_RE = re.compile(
    r"""
    \b(?P<value>\d+(?:\.\d+)?)\s*
    (?P<unit>seconds?|minutes?|hours?|days?|[smhd])\s+
    (?:
        after\s+(?:the\s+)?(?:\S+\s+){0,2}?(?:trigger|burst|explosion)
      | post[-\s]?(?:trigger|burst|explosion)
    )
    \b
    """,
    re.VERBOSE | re.IGNORECASE,
)

_UNIT_MAP: dict[str, TimeOffsetUnit] = {
    "s": "s", "sec": "s", "secs": "s", "second": "s", "seconds": "s",
    "m": "m", "min": "m", "mins": "m", "minute": "m", "minutes": "m",
    "h": "h", "hour": "h", "hours": "h",
    "d": "d", "day": "d", "days": "d",
}


def _normalize_unit(token: str) -> TimeOffsetUnit | None:
    return _UNIT_MAP.get(token.lower())


def parse_time_offsets(text: str) -> list[TimeOffset]:
    """Find all literal T+offset and 'X hours after trigger' phrasings."""
    return [t for t, _ in parse_time_offsets_with_spans(text)]


def parse_time_offsets_with_spans(text: str) -> list[tuple[TimeOffset, Span]]:
    """Same as parse_time_offsets, plus a Span per offset pointing at the phrasing."""
    out: list[tuple[TimeOffset, Span]] = []

    for match in _T_OFFSET_RE.finditer(text):
        unit = _normalize_unit(match.group("unit"))
        if unit is None:
            continue
        sign = match.group("sign")
        value = float(match.group("value"))
        if sign in ("-", "−", "–"):
            value = -value
            reference = "T-"
        else:
            reference = "T+"
        out.append((
            TimeOffset(value=value, unit=unit, reference=reference),
            Span(start=match.start(), end=match.end(), snippet=match.group(0)),
        ))

    for match in _POST_TRIGGER_RE.finditer(text):
        unit = _normalize_unit(match.group("unit"))
        if unit is None:
            continue
        out.append((
            TimeOffset(value=float(match.group("value")), unit=unit, reference="trigger"),
            Span(start=match.start(), end=match.end(), snippet=match.group(0)),
        ))

    return out
