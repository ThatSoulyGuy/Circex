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

# Labels, which circulars punctuate several ways: RA, R.A., R.A. (J2000).
_EPOCH = r"(?:\s*\((?:J2000(?:\.0)?|ICRS|FK5)\))?"
_RA_LABEL = r"\bR\.?\s?A\.?" + _EPOCH
_DEC_LABEL = r"\bDec(?:l)?\.?" + _EPOCH

# Interleaved labels: "RA = <ra> ... Dec = <dec>". The gap is [\s\S] rather than
# . so the pair can straddle a line break, which SVOM's discovery circulars do:
#   R.A. (J2000) = 22h37m45s
#   Dec. (J2000) = 53d14m02s
_PAIR_RE = re.compile(
    _RA_LABEL
    + r"\s*[=:]?\s*(?P<ra>"
    + _RA_INNER
    + r")[\s\S]{0,40}?"
    + _DEC_LABEL
    + r"\s*[=:]?\s*(?P<dec>"
    + _DEC_INNER
    + r")",
    re.IGNORECASE,
)

# Combined label then both values: "(RA, Dec) = <ra> <dec>" / "RA, Decl. = <ra> <dec>".
# The separator is optional because SVOM writes no "=" at all:
#   The localization of the best alert is R.A., Dec. 339.4431, 53.2195 degrees
_PAIR_COMBINED_RE = re.compile(
    r"\(?\s*" + _RA_LABEL + r"\s*,\s*" + _DEC_LABEL + r"\s*\)?\s*(?:[=:]\s*)?"
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
            coord = SkyCoord(float(ra_token), float(dec_token), unit=(u.deg, u.deg), frame="icrs")
    except Exception:
        return None

    span = Span(start=match.start(), end=match.end(), snippet=match.group(0))
    return (float(coord.ra.deg), float(coord.dec.deg)), span


# IPN triangulation error box, as the Konus-Wind/IPN circulars write it:
#
#     RA(2000), deg                 Dec(2000), deg
#    ---------------------------------------------
#    Center:
#     350.841 (23h 23m 22s) +12.853 (+12d 51' 11")
#
# The decimal degrees come first on the line, with the sexagesimal form in
# parentheses after each. These circulars carry the only position an IPN- or
# Konus-localized burst gets, so without this they extract no position at all.
_IPN_CENTER_RE = re.compile(
    r"Center:\s*\n\s*(?P<ra>\d{1,3}\.\d+)\s*(?:\([^)]*\))?\s*"
    r"(?P<dec>[+\-−]?\d{1,2}\.\d+)",
    re.IGNORECASE,
)

# "its maximum dimension is 2.45 deg (the minimum one is 19 arcmin)"
_IPN_DIMENSION_RE = re.compile(
    r"maximum\s+dimension\s+is\s+(?P<amaj>\d+(?:\.\d+)?)\s*(?P<amaj_unit>deg|arcmin)"
    r"(?:[^.]{0,60}?minimum\s+one\s+is\s+(?P<amin>\d+(?:\.\d+)?)\s*(?P<amin_unit>deg|arcmin))?",
    re.IGNORECASE,
)

_ARCMIN_PER_DEG = 60.0


def _to_degrees(value: str, unit: str) -> float:
    return float(value) / _ARCMIN_PER_DEG if unit.lower() == "arcmin" else float(value)


def parse_ipn_error_box(text: str) -> tuple[float, float, list[float] | None] | None:
    """Centre and extent of an IPN error box, as (ra, dec, [semi-major, semi-minor]).

    The extent is the stated box dimensions halved, in degrees; None when the
    circular gives a centre but no dimensions.
    """
    centre = _IPN_CENTER_RE.search(text)
    if centre is None:
        return None
    ra = float(centre.group("ra"))
    dec = float(centre.group("dec").replace("−", "-"))
    if not (0.0 <= ra <= 360.0 and -90.0 <= dec <= 90.0):
        return None

    extent: list[float] | None = None
    dims = _IPN_DIMENSION_RE.search(text)
    if dims is not None:
        amaj = _to_degrees(dims.group("amaj"), dims.group("amaj_unit")) / 2.0
        extent = [amaj]
        if dims.group("amin"):
            extent.append(_to_degrees(dims.group("amin"), dims.group("amin_unit")) / 2.0)
    return ra, dec, extent


def parse_ipn_error_box_with_span(
    text: str,
) -> tuple[tuple[float, float, list[float] | None], Span] | None:
    """Same as parse_ipn_error_box, plus the Span covering the centre line."""
    result = parse_ipn_error_box(text)
    if result is None:
        return None
    match = _IPN_CENTER_RE.search(text)
    assert match is not None  # parse_ipn_error_box just matched it
    return result, Span(start=match.start(), end=match.end(), snippet=match.group(0))
