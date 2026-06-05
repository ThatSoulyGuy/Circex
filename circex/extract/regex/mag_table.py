"""Magnitude parsers: single-row prose mentions + multi-row tables.

Per PDF Phase 2, multi-row tables are where regex visibly fails — the parser is
intentionally conservative. It should return ROWS on cleanly-formatted column-aligned
tables, and return NOTHING on irregular prose (rather than fabricating).

Mag-system inference rules (matching docs/labeling_spec.md):
  Sloan g/r/i/z/y → AB
  Bessel U/B/V/R/I → Vega
  2MASS J/H/K/Ks → Vega
"""

from __future__ import annotations

import re
from typing import Final

from circex.schema import MagSystem, PhotometryExt, Span

# Filter classification.
_SLOAN: Final[frozenset[str]] = frozenset({"u", "g", "r", "i", "z", "y"})
_BESSEL: Final[frozenset[str]] = frozenset({"U", "B", "V", "R", "I"})
_NIR: Final[frozenset[str]] = frozenset({"J", "H", "K", "Ks"})

_KNOWN_FILTERS: Final[frozenset[str]] = _SLOAN | _BESSEL | _NIR | frozenset({"clear", "C"})

# Single-mag patterns. Matches "r = 18.42 ± 0.05", "R=22.1+/-0.3", "K_s = 19.0",
# upper limits: "r > 22.5", "m > 22 (3-sigma)".
_DETECTION_RE = re.compile(
    r"""
    (?<![A-Za-z])                          # not preceded by a letter (avoid "Ar=...")
    (?P<filter>[UBVRIJHKgrizyuC]s?)         # filter
    \s*[=~]\s*
    (?P<mag>\d{1,2}\.\d{1,3})              # magnitude
    (?:\s*[±+\-]\s*(?P<err>\d+\.\d+))?     # optional error
    """,
    re.VERBOSE,
)

_UPPER_LIMIT_RE = re.compile(
    r"""
    (?<![A-Za-z])
    (?P<filter>[UBVRIJHKgrizyuC]s?)
    \s*>\s*
    (?P<limit>\d{1,2}\.\d{1,3})
    (?:.{0,40}?(?P<sigma>\d+(?:\.\d+)?)\s*[-–]?\s*sigma)?
    """,
    re.VERBOSE | re.IGNORECASE,
)


def infer_mag_system(filter_name: str) -> MagSystem | None:
    """Heuristic AB/Vega inference based on filter name conventions."""
    if filter_name in _SLOAN:
        return "AB"
    if filter_name in _BESSEL or filter_name in _NIR:
        return "Vega"
    return None


# Canonical-bandpass crosswalk (sncosmo / SkyPortal vocabulary). The raw filter
# token is always kept on PhotometryExt.filter; this populates the sibling
# `bandpass` field so downstream consumers (e.g. SkyPortal/ICARE) get a
# normalized name. `clear`/`C` (unfiltered) have no canonical bandpass.
_BANDPASS_CROSSWALK: Final[dict[str, str]] = {
    # Sloan (AB)
    "u": "sdssu", "g": "sdssg", "r": "sdssr", "i": "sdssi", "z": "sdssz",
    "y": "ps1::y",
    # Bessel (Vega)
    "U": "bessellu", "B": "bessellb", "V": "bessellv", "R": "bessellr", "I": "besselli",
    # 2MASS / NIR (Vega)
    "J": "2massj", "H": "2massh", "K": "2massks", "Ks": "2massks",
}


def infer_bandpass(filter_name: str) -> str | None:
    """Map a recognized filter token to its canonical bandpass name, or None."""
    return _BANDPASS_CROSSWALK.get(filter_name)


def _plausible_mag(filter_name: str, mag: float) -> bool:
    """Reject obvious non-photometric values (e.g., 'z = 1.61' for redshift).

    Photometric magnitudes are typically 5-30; the lowercase Sloan filter 'z'
    overlaps with redshift notation, so require z-band mags to be > 10.
    """
    if mag < 5.0:
        return False
    return not (filter_name == "z" and mag < 10.0)


def parse_single_mags(text: str) -> list[PhotometryExt]:
    """Extract single-row magnitude mentions ('r = 18.42 ± 0.05', 'R > 22.5')."""
    return [p for p, _ in parse_single_mags_with_spans(text)]


def parse_single_mags_with_spans(text: str) -> list[tuple[PhotometryExt, Span]]:
    """Same as parse_single_mags, plus per-row Spans into the source text."""
    rows: list[tuple[PhotometryExt, Span]] = []

    for match in _DETECTION_RE.finditer(text):
        filter_name = match.group("filter")
        if filter_name not in _KNOWN_FILTERS:
            continue
        mag = float(match.group("mag"))
        if not _plausible_mag(filter_name, mag):
            continue
        err = float(match.group("err")) if match.group("err") else None
        rows.append((
            PhotometryExt(
                filter=filter_name,
                mag=mag,
                mag_error=err,
                mag_system=infer_mag_system(filter_name),
                bandpass=infer_bandpass(filter_name),
            ),
            Span(start=match.start(), end=match.end(), snippet=match.group(0)),
        ))

    for match in _UPPER_LIMIT_RE.finditer(text):
        filter_name = match.group("filter")
        if filter_name not in _KNOWN_FILTERS:
            continue
        limit = float(match.group("limit"))
        sigma = float(match.group("sigma")) if match.group("sigma") else None
        rows.append((
            PhotometryExt(
                filter=filter_name,
                limiting_mag=limit,
                limiting_mag_sigma=sigma,
                mag_system=infer_mag_system(filter_name),
                bandpass=infer_bandpass(filter_name),
            ),
            Span(start=match.start(), end=match.end(), snippet=match.group(0)),
        ))

    return rows


# ---- Multi-row table detector ----

_COLUMN_SPLIT_RE = re.compile(r"\s{2,}|\t")
_HEADER_KEYWORDS = {"date", "mjd", "epoch", "filter", "band", "mag", "magnitude",
                    "err", "error", "exp", "exptime", "exposure"}


def _looks_like_header(line: str) -> bool:
    """Cheap heuristic: line is a header if it contains 2+ table keywords."""
    tokens = {token.strip(":").lower() for token in _COLUMN_SPLIT_RE.split(line)}
    return len(tokens & _HEADER_KEYWORDS) >= 2


def _looks_like_table_row(line: str, expected_columns: int) -> bool:
    """A data row has roughly the expected number of fields and at least one numeric."""
    fields = [f for f in _COLUMN_SPLIT_RE.split(line.strip()) if f]
    if not (expected_columns - 1 <= len(fields) <= expected_columns + 1):
        return False
    return any(re.search(r"\d", f) for f in fields)


def _classify_columns(header_line: str) -> dict[int, str]:
    """Return a dict mapping column index -> semantic role (filter, mag, err, ...)."""
    fields = [f.strip(":").lower() for f in _COLUMN_SPLIT_RE.split(header_line) if f]
    classification: dict[int, str] = {}
    for i, token in enumerate(fields):
        if token in {"filter", "band"}:
            classification[i] = "filter"
        elif token in {"mag", "magnitude"}:
            classification[i] = "mag"
        elif token in {"err", "error", "magerr", "merr"}:
            classification[i] = "mag_error"
        elif token in {"date", "mjd", "epoch"}:
            classification[i] = "date"
        elif token in {"exp", "exptime", "exposure"}:
            classification[i] = "exposure"
    return classification


def parse_mag_table(text: str) -> list[PhotometryExt]:
    """Detect column-aligned magnitude tables and parse rows.

    Conservative: requires an explicit header line with table keywords. Prose-style
    "we measured r = 18.42" is NOT picked up here (use parse_single_mags). This
    parser is the one that the PDF expects to lose on irregular table layouts.
    """
    return [p for p, _ in parse_mag_table_with_spans(text)]


def parse_mag_table_with_spans(text: str) -> list[tuple[PhotometryExt, Span]]:
    """Same as parse_mag_table, plus per-row Spans covering each data line."""
    rows: list[tuple[PhotometryExt, Span]] = []
    # Use keepends=True so we can compute absolute offsets for each line.
    lines = text.splitlines(keepends=True)
    line_offsets: list[int] = [0]
    for line in lines:
        line_offsets.append(line_offsets[-1] + len(line))

    i = 0
    while i < len(lines):
        line = lines[i]
        if not _looks_like_header(line):
            i += 1
            continue

        cols = _classify_columns(line)
        if "filter" not in cols.values() or "mag" not in cols.values():
            i += 1
            continue

        header_fields = [f for f in _COLUMN_SPLIT_RE.split(line.strip()) if f]
        expected = len(header_fields)

        j = i + 1
        while j < len(lines) and _looks_like_table_row(lines[j], expected):
            data_fields = [f for f in _COLUMN_SPLIT_RE.split(lines[j].strip()) if f]
            row_data: dict[str, str] = {}
            for idx, role in cols.items():
                if idx < len(data_fields):
                    row_data[role] = data_fields[idx]

            filter_token = row_data.get("filter")
            mag_token = row_data.get("mag")
            if filter_token and mag_token:
                try:
                    mag = float(mag_token)
                except ValueError:
                    j += 1
                    continue
                err: float | None = None
                if (err_token := row_data.get("mag_error")) is not None:
                    try:
                        err = float(err_token)
                    except ValueError:
                        err = None
                row_start = line_offsets[j]
                row_text = lines[j].rstrip("\r\n")
                row_end = row_start + len(row_text)
                rows.append((
                    PhotometryExt(
                        filter=filter_token,
                        mag=mag,
                        mag_error=err,
                        mag_system=infer_mag_system(filter_token),
                        bandpass=infer_bandpass(filter_token),
                    ),
                    Span(start=row_start, end=row_end, snippet=row_text),
                ))
            j += 1
        i = j if j > i + 1 else i + 1

    return rows
