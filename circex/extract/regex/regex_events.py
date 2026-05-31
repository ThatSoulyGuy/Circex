"""Event-name regex extraction.

Originally ported from sjhend03/GCNMCP src/utils.py; extended in Sprint 2 with
TNS-style AT/SN suffixes (lowercase letter run), ZTF, ATLAS, ASAS-SN, Pan-STARRS,
GOTO, plus GCN cross-reference extraction.
"""

from __future__ import annotations

import re
from typing import Any

EVENT_PATTERNS: list[str] = [
    # GRB: 6-digit YYMMDD + optional uppercase letter (e.g., GRB 230307A).
    r"\b(GRB\s?\d{6}[A-Z]?)\b",
    # Einstein Probe (2024+): EP240617A.
    r"\b(EP\s?\d+[A-Z]?)\b",
    # TNS designations (modern): AT2017gfo, AT 2018cow, SN 2024abc.
    r"\b(AT\s?\d{4}[a-z]+)\b",
    r"\b(SN\s?\d{4}[a-z]+)\b",
    # Old-style AT/SN with uppercase single-letter suffix (pre-TNS era).
    r"\b(AT\s?\d{2,4}[A-Z])\b",
    r"\b(SN\s?\d{2,4}[A-Z])\b",
    # ZTF survey: ZTF21aaqkqfp (2-digit year + lowercase letters).
    r"\b(ZTF\d{2}[a-z]+)\b",
    # ATLAS survey: ATLAS24abc.
    r"\b(ATLAS\s?-?\d{2}[a-z]+)\b",
    # ASAS-SN survey: ASASSN-19abc.
    r"\b(ASASSN[-\s]?\d{2}[a-z]+)\b",
    # Pan-STARRS: PS22ggn or Pan-STARRS 22abc.
    r"\b(PS\d{2}[a-z]+)\b",
    r"\b(Pan-?STARRS\s?\d{2}[a-z]+)\b",
    # GOTO: GOTO24abc.
    r"\b(GOTO\s?\d{2}[a-z]+)\b",
    # IceCube: ICECUBE-200107A or IceCube 191001A.
    r"\b(ICECUBE\s?-?\d+[A-Z]?)\b",
    # Swift X-ray catalog: SWIFT J1234.5+6789.0.
    r"\b(SWIFT\s?J\d+(?:\.\d+)?[+-]\d+(?:\.\d+)?)\b",
]

# GCN cross-reference: "GCN #12345", "GCN Circular 12345", "GCN Circ. #12345".
# Stored separately from event names — used to populate follow_up.reference.
GCN_XREF_PATTERN = re.compile(
    r"\bGCN\s*(?:Circ(?:ular|\.)?\s*)?#?\s*(\d{1,7})\b",
    re.IGNORECASE,
)


def extract_gcn_xrefs(text: str) -> list[int]:
    """Return all GCN Circular cross-reference IDs from text, deduplicated, in order."""
    return [cid for cid, _, _ in extract_gcn_xrefs_with_positions(text)]


def extract_gcn_xrefs_with_positions(text: str) -> list[tuple[int, int, int]]:
    """As extract_gcn_xrefs, returning (cid, start, end) tuples per first occurrence."""
    seen: set[int] = set()
    out: list[tuple[int, int, int]] = []
    for match in GCN_XREF_PATTERN.finditer(text):
        cid = int(match.group(1))
        if cid not in seen:
            seen.add(cid)
            out.append((cid, match.start(), match.end()))
    return out


def clean_text(text: str | None) -> str:
    """Normalize text: None -> "", null bytes removed, whitespace trimmed."""
    if text is None:
        return ""
    return text.replace("\x00", " ").strip()


def normalize_event(event: str | None) -> str | None:
    """Uppercase + whitespace-strip an event name. None/empty returns None."""
    if not event:
        return None
    return re.sub(r"\s+", "", event).upper()


def extract_matches(text: str) -> list[str]:
    """Find all event-like identifiers in text. Returns deduplicated, ordered by position."""
    return [name for name, _, _ in extract_matches_with_positions(text)]


def extract_matches_with_positions(text: str) -> list[tuple[str, int, int]]:
    """As extract_matches, but each entry is (normalized_name, start, end)."""
    found: list[tuple[int, int, str]] = []

    for pattern in EVENT_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            raw = match.group(1)
            norm = normalize_event(raw)
            if norm:
                found.append((match.start(), match.end(), norm))
    found.sort(key=lambda x: x[0])

    results: list[tuple[str, int, int]] = []
    seen: set[str] = set()
    for start, end, norm in found:
        if norm not in seen:
            seen.add(norm)
            results.append((norm, start, end))
    return results


def extract_events(record: dict[str, Any]) -> tuple[str | None, list[str], str]:
    """Extract primary event from a circular record.

    Precedence: eventId field -> subject -> body.

    Returns:
        primary_event_raw: best raw event string, or None
        all_events: all normalized events found
        source: one of {"eventId", "subject", "body", "none"}
    """
    raw, all_events, source, _, _ = extract_events_with_position(record)
    return raw, all_events, source


def extract_events_with_position(
    record: dict[str, Any],
) -> tuple[str | None, list[str], str, int, int]:
    """As extract_events, plus (start, end) of the primary match in its source string.

    Offsets are valid only when source is "subject" or "body". When source is
    "eventId" or "none", start and end are returned as -1, -1.
    """
    event_id = clean_text(record.get("eventId"))
    if event_id:
        event_norm = normalize_event(event_id)
        return event_id, ([event_norm] if event_norm else []), "eventId", -1, -1

    subject = clean_text(record.get("subject"))
    subj_matches = extract_matches_with_positions(subject)
    if subj_matches:
        name, start, end = subj_matches[0]
        return name, [m[0] for m in subj_matches], "subject", start, end

    body = clean_text(record.get("body"))
    body_matches = extract_matches_with_positions(body)
    if body_matches:
        name, start, end = body_matches[0]
        return name, [m[0] for m in body_matches], "body", start, end

    return None, [], "none", -1, -1


def extract_event_from_query(query: str) -> str | None:
    """Pull the first event from a user query string."""
    matches = extract_matches(query)
    return matches[0] if matches else None
