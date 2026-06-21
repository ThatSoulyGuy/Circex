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

from typing import Any

from circex.schema import CircularExtraction, Span

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
