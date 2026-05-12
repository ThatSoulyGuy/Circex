"""RegexExtractor — composes the regex sub-extractors into a CircularExtraction.

This is the baseline the LLM extractor must beat on per-field P/R/F1. Per the PDF,
regex is EXPECTED to fail visibly on multi-row mag tables and in-prose
classifications — measure the gap, do not over-engineer.
"""

from __future__ import annotations

import time
from typing import Final

from circex.extract.protocol import Circular, Extractor
from circex.extract.regex.classification import parse_classification
from circex.extract.regex.coords import parse_coords
from circex.extract.regex.dates import parse_time_offsets
from circex.extract.regex.mag_table import parse_mag_table, parse_single_mags
from circex.extract.regex.redshift import parse_redshift
from circex.extract.regex.regex_events import extract_events, extract_gcn_xrefs
from circex.schema import (
    CircularExtraction,
    Event,
    ExtractionMeta,
    FollowUp,
    Localization,
)

REGEX_EXTRACTOR_ID: Final[str] = "regex-v1"


class RegexExtractor(Extractor):
    """Regex baseline. Implements the Extractor protocol."""

    @property
    def extractor_id(self) -> str:
        return REGEX_EXTRACTOR_ID

    def extract(self, circular: Circular) -> CircularExtraction:
        started = time.perf_counter()
        body = circular.body
        subject = circular.subject

        # ---- event identification ----
        record = {"eventId": circular.event_id, "subject": subject, "body": body}
        primary_event_raw, _, _ = extract_events(record)
        event: Event | None = None
        if primary_event_raw:
            event = Event(event_name=primary_event_raw)

        # ---- GCN cross-references → follow_up ----
        xrefs = extract_gcn_xrefs(body)
        follow_up: FollowUp | None = None
        if xrefs:
            follow_up = FollowUp(
                reference={"gcn_circulars": ",".join(str(x) for x in xrefs)},
            )

        # ---- localization ----
        localization: Localization | None = None
        if (coords := parse_coords(body)) is not None:
            ra, dec = coords
            localization = Localization(ra=ra, dec=dec)

        # ---- photometry: prefer table over prose ----
        table_rows = parse_mag_table(body)
        photometry = table_rows if table_rows else parse_single_mags(body)

        # ---- redshift, classification, time offsets ----
        redshift = parse_redshift(body)
        classification = parse_classification(body)
        time_offsets = parse_time_offsets(body)

        latency_ms = (time.perf_counter() - started) * 1000.0

        return CircularExtraction(
            circular_id=circular.circular_id,
            event=event,
            follow_up=follow_up,
            localization=localization,
            time_offsets=time_offsets,
            photometry=photometry,
            classification=classification,
            redshift=redshift,
            extraction_meta=ExtractionMeta(
                extractor=REGEX_EXTRACTOR_ID,
                latency_ms=latency_ms,
            ),
        )
