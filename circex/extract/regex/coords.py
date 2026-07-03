"""Sexagesimal RA/Dec parser via astropy.

Accepts the common circular notations:
  - "RA = 12h34m56.7s, Dec = -23d45m12.3s"
  - "RA = 12:34:56.7, Dec = -23:45:12.3"
  - "(J2000) 12h34m56.7s -23d45m12.3s"
  - "(RA, Dec) = 14h 57m 49.59s +28d 49m 03.0s"  (combined label, space-separated)
  - Decimal degrees: "RA = 191.532, Dec = -23.7534"

Always returns decimal degrees in ICRS J2000. None if no pair is found.
"""

from __future__ import annotations

import re

import astropy.units as u
from astropy.coordinates import SkyCoord

from circex.schema import Span

# Reusable RA / Dec value sub-patterns (shared by both pair regexes below).
# Each accepts sexagesimal (with optional interior spaces), decimal degrees, or a
# bare integer-degree fallback.
_RA_INNER = (
    r"(?:\d{1,2}[h:]\s*\d{1,2}[m:]\s*\d{1,2}(?:\.\d+)?s?"  # 12h34m56.7s / 12:34:56.7
    r"|\d{1,3}\.\d+"  # 191.532 decimal degrees
    r"|\d{1,3})"  # 191 (fallback)
)
_DEC_INNER = (
    r"(?:[+\-]?\d{1,2}[d°:]\s*\d{1,2}[m':]\s*\d{1,2}(?:\.\d+)?[s\"]?"
    r"|[+\-]?\d{1,2}\.\d+"
    r"|[+\-]?\d{1,2})"
)

# Interleaved labels: "RA = <ra> ... Dec = <dec>".
_PAIR_RE = re.compile(
    r"\bRA\s*[=:]?\s*(?P<ra>" + _RA_INNER + r").{0,40}?"
    r"\bDec(?:l?)\s*[=:]?\s*(?P<dec>" + _DEC_INNER + r")",
    re.IGNORECASE,
)

# Combined label then both values: "(RA, Dec) = <ra> <dec>" / "RA, Decl. = <ra> <dec>".
# The two values are separated by whitespace (with an optional comma).
_PAIR_COMBINED_RE = re.compile(
    r"\(?\s*RA\s*,\s*Dec(?:l?)\.?\s*\)?\s*[=:]\s*"
    r"(?P<ra>" + _RA_INNER + r")\s*,?\s+(?P<dec>" + _DEC_INNER + r")",
    re.IGNORECASE,
)


def _parse_one_ra(token: str) -> str:
    """Normalize an RA token into a string astropy can parse."""
    token = token.replace(" ", "")
    if ":" in token:
        return token  # 12:34:56.7
    if "h" in token.lower():
        return token  # 12h34m56.7s
    return token  # decimal degrees


def _parse_one_dec(token: str) -> str:
    token = token.replace(" ", "")
    # Replace ASCII colons with explicit DMS letters if it's sexagesimal; SkyCoord
    # accepts colons only with explicit unit hints.
    return token


def parse_coords(text: str) -> tuple[float, float] | None:
    """Find the first RA/Dec pair in text and return (ra_deg, dec_deg) ICRS J2000."""
    result = parse_coords_with_span(text)
    return result[0] if result is not None else None


def parse_coords_with_span(
    text: str,
) -> tuple[tuple[float, float], Span] | None:
    """Same as parse_coords, but also return a Span covering the RA/Dec match."""
    match = _PAIR_RE.search(text) or _PAIR_COMBINED_RE.search(text)
    if not match:
        return None

    ra_token = _parse_one_ra(match.group("ra"))
    dec_token = _parse_one_dec(match.group("dec"))

    sexagesimal = bool(re.search(r"[hHmMsSdDoO':\"°]", ra_token + dec_token))

    try:
        if sexagesimal:
            coord = SkyCoord(ra_token, dec_token, unit=(u.hourangle, u.deg), frame="icrs")
        else:
            coord = SkyCoord(
                float(ra_token), float(dec_token), unit=(u.deg, u.deg), frame="icrs"
            )
    except Exception:
        return None

    span = Span(start=match.start(), end=match.end(), snippet=match.group(0))
    return (float(coord.ra.deg), float(coord.dec.deg)), span
