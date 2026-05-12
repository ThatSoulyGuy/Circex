"""Sexagesimal RA/Dec parser via astropy.

Accepts the common circular notations:
  - "RA = 12h34m56.7s, Dec = -23d45m12.3s"
  - "RA = 12:34:56.7, Dec = -23:45:12.3"
  - "(J2000) 12h34m56.7s -23d45m12.3s"
  - Decimal degrees: "RA = 191.532, Dec = -23.7534"

Always returns decimal degrees in ICRS J2000. None if no pair is found.
"""

from __future__ import annotations

import re

import astropy.units as u
from astropy.coordinates import SkyCoord

# Capture both halves of an RA/Dec pair in one go.
# Group 1 = RA, group 2 = Dec.
_PAIR_RE = re.compile(
    r"""
    \bRA\s*[=:]?\s*
    (?P<ra>
        \d{1,2}[h:]\s*\d{1,2}[m:]\s*\d{1,2}(?:\.\d+)?s? |   # 12h34m56.7s or 12:34:56.7
        \d{1,3}\.\d+ |                                       # 191.532 decimal degrees
        \d{1,3}                                              # 191 (degrees, fallback)
    )
    .{0,40}?
    \bDec(?:l?)\s*[=:]?\s*
    (?P<dec>
        [+\-]?\d{1,2}[d°:]\s*\d{1,2}[m':]\s*\d{1,2}(?:\.\d+)?[s\"]? |
        [+\-]?\d{1,2}\.\d+ |
        [+\-]?\d{1,2}
    )
    """,
    re.VERBOSE | re.IGNORECASE,
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
    match = _PAIR_RE.search(text)
    if not match:
        return None

    ra_token = _parse_one_ra(match.group("ra"))
    dec_token = _parse_one_dec(match.group("dec"))

    # Heuristic: if either token contains h/m/s/d/' or colons, treat as sexagesimal;
    # otherwise treat as decimal degrees.
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

    return float(coord.ra.deg), float(coord.dec.deg)
