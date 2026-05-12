"""Event-name regex extraction. Ported from sjhend03/GCNMCP src/utils.py.

Sprint 2 will extend EVENT_PATTERNS with TNS, ZTF, ATLAS, ASAS-SN, Pan-STARRS,
GOTO, and a GCN cross-reference pattern. Sprint 0 keeps the predecessor set.
"""

from __future__ import annotations

import re
from typing import Any

EVENT_PATTERNS: list[str] = [
    r"\b(GRB\s?\d{6}[A-Z]?)\b",
    r"\b(EP\s?\d+[A-Z]?)\b",
    r"\b(AT\s?\d+[A-Z]?)\b",
    r"\b(SN\s?\d+[A-Z]?)\b",
    r"\b(ICECUBE\s?-?\d+[A-Z]?)\b",
    r"\b(SWIFT\s?J\d+(?:\.\d+)?[+-]\d+(?:\.\d+)?)\b",
]


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
    found: list[tuple[int, str]] = []

    for pattern in EVENT_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            raw = match.group(1)
            norm = normalize_event(raw)
            if norm:
                found.append((match.start(), norm))
    found.sort(key=lambda x: x[0])

    results: list[str] = []
    seen: set[str] = set()
    for _, norm in found:
        if norm not in seen:
            seen.add(norm)
            results.append(norm)
    return results


def extract_events(record: dict[str, Any]) -> tuple[str | None, list[str], str]:
    """Extract primary event from a circular record.

    Precedence: eventId field -> subject -> body.

    Returns:
        primary_event_raw: best raw event string, or None
        all_events: all normalized events found
        source: one of {"eventId", "subject", "body", "none"}
    """
    event_id = clean_text(record.get("eventId"))
    if event_id:
        event_norm = normalize_event(event_id)
        return event_id, ([event_norm] if event_norm else []), "eventId"

    subject = clean_text(record.get("subject"))
    subject_matches = extract_matches(subject)
    if subject_matches:
        return subject_matches[0], subject_matches, "subject"

    body = clean_text(record.get("body"))
    body_matches = extract_matches(body)
    if body_matches:
        return body_matches[0], body_matches, "body"

    return None, [], "none"


def extract_event_from_query(query: str) -> str | None:
    """Pull the first event from a user query string."""
    matches = extract_matches(query)
    return matches[0] if matches else None
