"""Flatten a CircularExtraction into a per-field {value, snippet} map.

Built for snippet-level human validation (e.g. tylerbarna/gcn-nlp-label): a flat
dict keyed by field name, each value an object carrying the extracted value AND
the source-text snippet it came from, so a reviewer can confirm each value
against the exact phrase. Pairs every populated leaf with its provenance span —
leaf-level when the extractor emitted it, else the parent object's span.

    {
      "event_name": {"value": "AT2026xyz", "snippet": "AT2026xyz", "start": 0, "end": 9},
      "ra":         {"value": "224.512",  "snippet": "RA = 224.512, Dec = +28.804", ...},
      "redshift":   {"value": "0.512",    "snippet": "z = 0.512", "start": 315, "end": 324},
      ...
    }

A consumer that wants only the value reads `.value` (matching the
`normalizeExtraction` CASE 2 in gcn-nlp-label); a validation UI shows `.snippet`.
"""

from __future__ import annotations

import re
from typing import Any

from circex.schema import CircularExtraction, Span

# photometry[0].mag -> photometry[0] : anchor list-row matches at the row object so
# every sibling field inherits the row's snippet via the parent fallback.
_INDEXED_PARENT_RE = re.compile(r"^(.*\[\d+\])(?:\.|$)")

# Schema fields that aren't extracted values to validate.
_SKIP_TOP = {"circular_id", "provenance", "extraction_meta"}


def _find_span(provenance: dict[str, Span], path: str) -> Span | None:
    """Provenance for `path`: exact leaf match, else the nearest parent object.

    'localization.ra' -> try 'localization.ra', then 'localization'.
    'photometry[0].mag' -> try 'photometry[0].mag', then 'photometry[0]'.
    """
    probe = path
    while probe:
        if probe in provenance:
            return provenance[probe]
        if "." not in probe:
            return None
        probe = probe.rsplit(".", 1)[0]
    return None


def _walk(
    value: Any, path: str, provenance: dict[str, Span], out: dict[str, dict[str, Any]]
) -> None:
    if isinstance(value, dict):
        for key, sub in value.items():
            _walk(sub, f"{path}.{key}" if path else str(key), provenance, out)
    elif isinstance(value, list):
        if value and all(not isinstance(it, dict | list) for it in value):
            # list of scalars (e.g. event_name) -> one joined field
            _emit(value, path, provenance, out)
        else:
            for i, item in enumerate(value):
                _walk(item, f"{path}[{i}]", provenance, out)
    elif value is not None and value != "":
        _emit(value, path, provenance, out)


def _emit(
    value: Any, path: str, provenance: dict[str, Span], out: dict[str, dict[str, Any]]
) -> None:
    span = _find_span(provenance, path)
    record: dict[str, Any] = {"value": _stringify(value), "snippet": None}
    if span is not None:
        record["snippet"] = span.snippet
        record["start"] = span.start
        record["end"] = span.end
    out[path] = record


def _stringify(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _iter_leaves(value: Any, path: str, out: list[tuple[str, Any]]) -> None:
    """Collect (path, value) for every populated leaf — mirrors ``_walk``."""
    if isinstance(value, dict):
        for key, sub in value.items():
            _iter_leaves(sub, f"{path}.{key}" if path else str(key), out)
    elif isinstance(value, list):
        if value and all(not isinstance(it, dict | list) for it in value):
            out.append((path, value))
        else:
            for i, item in enumerate(value):
                _iter_leaves(item, f"{path}[{i}]", out)
    elif value is not None and value != "":
        out.append((path, value))


def _candidate_strings(value: Any) -> list[str]:
    """Literal strings to search for a value, longest-confidence first.

    Values under 3 chars (``"r"``, ``"Ia"``) are skipped — they match almost
    anywhere and would only mislead a validator.
    """
    raw: list[str] = []
    if isinstance(value, list):
        raw.extend(str(v) for v in value)
    else:
        raw.append(str(value))
        if isinstance(value, float):
            if value.is_integer():
                raw.append(str(int(value)))
            raw.append(f"{value:g}")
    out: list[str] = []
    for s in raw:
        if len(s) >= 3 and s not in out:
            out.append(s)
    return out


def _line_span(body: str, i: int, j: int, max_len: int = 200) -> tuple[int, int]:
    """The line containing ``body[i:j]``, clipped to ``max_len`` around the match."""
    ls = body.rfind("\n", 0, i) + 1
    le = body.find("\n", j)
    if le == -1:
        le = len(body)
    if le - ls > max_len:
        ls = max(ls, i - max_len // 2)
        le = min(le, j + max_len // 2)
    return ls, le


def backfill_spans(extraction: CircularExtraction, body: str) -> int:
    """Attach best-effort provenance for populated leaves that have none.

    LLM extractors run under a lean grammar emit no provenance, so their values
    reach a snippet-level validator bare. This recovers a snippet by locating the
    value's text in ``body`` — but only on a *unique* match: a value absent from
    the body, or appearing more than once (e.g. a magnitude repeated across table
    rows), is left alone rather than risk pointing the validator at the wrong
    occurrence. Mutates ``extraction.provenance`` in place; returns the count added.
    """
    dump = extraction.model_dump(mode="json", by_alias=False, exclude_none=True)
    leaves: list[tuple[str, Any]] = []
    for key, value in dump.items():
        if key in _SKIP_TOP:
            continue
        _iter_leaves(value, key, leaves)

    provenance = extraction.provenance
    added = 0
    for path, value in leaves:
        if _find_span(provenance, path) is not None:
            continue
        for needle in _candidate_strings(value):
            first = body.find(needle)
            if first == -1:
                continue
            if body.find(needle, first + 1) != -1:
                break  # ambiguous — more than one occurrence, don't guess
            start, end = _line_span(body, first, first + len(needle))
            # Anchor a list-row match at the row object so the row's other fields
            # (derived MJD, canonical bandpass) inherit the snippet; scalar leaves
            # anchor on themselves.
            match = _INDEXED_PARENT_RE.match(path)
            anchor = match.group(1) if match else path
            provenance.setdefault(anchor, Span(start=start, end=end, snippet=body[start:end]))
            added += 1
            break
    return added


def to_label_fields(extraction: CircularExtraction) -> dict[str, dict[str, Any]]:
    """Flat {field_path: {value, snippet, start?, end?}} for every populated value.

    `snippet` is null when the extractor recorded no provenance for that field
    (or its parent). Keys are dotted/indexed paths (`localization.ra`,
    `photometry[0].mag`).
    """
    dump = extraction.model_dump(mode="json", by_alias=False, exclude_none=True)
    provenance = extraction.provenance
    out: dict[str, dict[str, Any]] = {}
    for key, value in dump.items():
        if key in _SKIP_TOP:
            continue
        _walk(value, key, provenance, out)
    return out
