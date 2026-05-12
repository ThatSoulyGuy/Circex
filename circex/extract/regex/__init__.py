"""Regex baseline extractors.

Sprint 2 deliverable: a RegexExtractor that produces CircularExtraction objects.
Composed of independent sub-extractors (coords, dates, mag_table, redshift,
classification, regex_events). Per the PDF, regex is EXPECTED to fail on
multi-row mag tables — that's the point of the baseline.
"""

from circex.extract.regex.extractor import RegexExtractor
from circex.extract.regex.regex_events import (
    EVENT_PATTERNS,
    GCN_XREF_PATTERN,
    clean_text,
    extract_event_from_query,
    extract_events,
    extract_gcn_xrefs,
    extract_matches,
    normalize_event,
)

__all__ = [
    "EVENT_PATTERNS",
    "GCN_XREF_PATTERN",
    "RegexExtractor",
    "clean_text",
    "extract_event_from_query",
    "extract_events",
    "extract_gcn_xrefs",
    "extract_matches",
    "normalize_event",
]
