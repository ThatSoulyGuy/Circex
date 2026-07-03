"""Observation-epoch resolution for photometry rows (ICARE P0 #2).

Two sources of a row's epoch:

1. An absolute UT / MJD stated in the row (a table's Date/MJD column) — parsed
   here with no trigger time needed.
2. A relative offset ("T+234s") plus a trigger time T0 — resolved here.

Both produce an `(obs_mjd, obs_time)` pair: MJD (UTC) as a float and an ISO-8601
UTC string. T0 is treated as immutable per circular (true for a published GRB
trigger), so resolving relative offsets at extraction time and caching the
result is safe.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from astropy.time import Time
from dateutil import parser as date_parser

from circex.schema import CircularExtraction

# Plausible MJD range so a bare number is read as MJD, not a year or a count:
# 40000 = 1968-05-24, 90000 = 2031-09-04. GCN circulars fall well inside this.
_MJD_LO = 40000.0
_MJD_HI = 90000.0

_UNIT_SECONDS: dict[str, float] = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}


def _to_pair(dt_or_mjd: datetime | float) -> tuple[float, str]:
    """Normalize a datetime or MJD float to (obs_mjd, obs_time ISO-8601 UTC)."""
    if isinstance(dt_or_mjd, datetime):
        dt = dt_or_mjd if dt_or_mjd.tzinfo else dt_or_mjd.replace(tzinfo=UTC)
        t = Time(dt.astimezone(UTC))
        return float(t.mjd), dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
    t = Time(dt_or_mjd, format="mjd")
    iso = str(t.utc.isot)
    return float(dt_or_mjd), iso if iso.endswith("Z") else iso + "Z"


def epoch_from_absolute(token: str | None) -> tuple[float, str] | None:
    """Parse an absolute date/MJD token into (obs_mjd, obs_time), or None.

    Accepts bare MJD numbers (within the plausible range), ISO-8601, and the
    loose 'YYYY-MM-DD HH:MM' forms common in circular tables.
    """
    if not token:
        return None
    token = token.strip()
    if not token:
        return None
    # Bare MJD number.
    try:
        val = float(token)
    except ValueError:
        pass
    else:
        if _MJD_LO < val < _MJD_HI:
            return _to_pair(val)
        return None  # a number outside MJD range isn't a date we trust
    # Calendar date/time.
    try:
        dt = date_parser.parse(token)
    except (ValueError, OverflowError):
        return None
    return _to_pair(dt)


def normalize_pair(
    obs_mjd: float | None, obs_time: str | None
) -> tuple[float, str] | None:
    """Given whichever of (obs_mjd, obs_time) is set, return both. None if neither.

    obs_mjd wins when both are present (numeric, unambiguous). Used to backfill
    the missing half of the pair on PhotometryExt (e.g. an LLM that set only the
    ISO time).
    """
    if obs_mjd is not None:
        return _to_pair(obs_mjd)
    return epoch_from_absolute(obs_time)


def epoch_from_offset(
    trigger_time: datetime, value: float, unit: str
) -> tuple[float, str] | None:
    """Resolve T0 + offset into (obs_mjd, obs_time). None if the unit is unknown."""
    seconds = _UNIT_SECONDS.get(unit)
    if seconds is None:
        return None
    base = trigger_time if trigger_time.tzinfo else trigger_time.replace(tzinfo=UTC)
    mjd = float(Time(base.astimezone(UTC)).mjd) + (value * seconds) / 86400.0
    return _to_pair(mjd)


# An absolute observation datetime stated in prose, near observation language:
# "We observed from 2026-06-05 03:41 to 03:51 UTC", "images obtained on
# 2026-06-08 20:01". Captures the first datetime that follows an observation verb.
_OBS_EPOCH_RE = re.compile(
    r"(?:observ|imag|obtain|acquir|expos|integrat)\w*[^.\n]{0,60}?"
    r"(\d{4}[-.]\d{2}[-.]\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?)",
    re.IGNORECASE,
)


def parse_observation_epoch(text: str) -> tuple[float, str] | None:
    """First absolute observation datetime stated in prose, as (obs_mjd, obs_time).

    Looks for a calendar datetime immediately following observation language
    ("observed ... 2026-06-05 03:41"). Used to time prose photometry lists whose
    epoch lives in a separate sentence rather than a per-row column. None if none.
    """
    match = _OBS_EPOCH_RE.search(text)
    if match is None:
        return None
    return epoch_from_absolute(match.group(1))


def resolve_observation_epoch(extraction: CircularExtraction, body: str) -> None:
    """Backfill a single circular-level observation epoch onto untimed rows, in place.

    For prose photometry lists ("g = 19.69 +/- 0.04", magnitudes on their own
    lines) the observation time is stated once, in a separate sentence, not per
    row. When EVERY photometry row lacks an epoch and the body states one
    observation datetime, apply it to all rows. Guarded to all-untimed so a
    partially-dated table is never clobbered; notes the inference for the record.
    """
    if not extraction.photometry:
        return
    if any(r.obs_mjd is not None or r.obs_time is not None for r in extraction.photometry):
        return
    pair = parse_observation_epoch(body)
    if pair is None:
        return
    mjd, iso = pair
    for row in extraction.photometry:
        row.obs_mjd = mjd
        row.obs_time = iso
    extraction.extraction_meta.notes.append(
        f"observation epoch {iso} (single circular-level time) applied to all "
        f"{len(extraction.photometry)} photometry row(s)"
    )


def resolve_relative_epochs(
    extraction: CircularExtraction, trigger_time: datetime | None
) -> None:
    """Fill obs_mjd/obs_time on rows that lack an epoch, in place.

    Conservative single-epoch rule: only applied when the circular has exactly
    one distinct relative offset (one time_offset, or several that resolve to
    the same MJD) and a trigger time is known. That single epoch is applied to
    every photometry row still missing a time. Multiple distinct offsets are
    ambiguous to pair with rows, so those are left null rather than guessed.
    """
    if trigger_time is None or not extraction.photometry:
        return
    resolved: set[tuple[float, str]] = set()
    for off in extraction.time_offsets:
        pair = epoch_from_offset(trigger_time, off.value, off.unit)
        if pair is not None:
            resolved.add(pair)
    if len(resolved) != 1:
        return
    (mjd, iso) = next(iter(resolved))
    for row in extraction.photometry:
        if row.obs_mjd is None and row.obs_time is None:
            row.obs_mjd = mjd
            row.obs_time = iso
