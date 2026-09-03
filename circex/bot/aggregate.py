"""Aggregate an event's circulars into ONE SkyPortal source.

The single-circular path (`circex post`) posts one bulletin at a time. A real
transient is described across many circulars — a discovery circular carries the
position, follow-ups carry the light curve. `aggregate_event` fuses them:

  - position preferring the refined optical-counterpart circular over a coarse
    gamma-ray trigger box (which can be degrees off),
  - photometry unioned across every circular (each point keeps its own source
    circular id in altdata),
  - deduped so a re-run or an overlapping report doesn't double-post,
  - a single redshift if any circular states a valid one.

`gather_by_xref` discovers an event's circulars from a seed by walking the GCN
cross-reference graph the extractor already recovers — no event-search API needed.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any

from circex.bot.skyportal_map import SkyPortalActions, SourceUpsert, to_actions
from circex.extract.protocol import Circular, Extractor
from circex.extract.regex.regex_events import extract_gcn_xrefs_with_positions
from circex.schema import Event

# Prefer a refined optical-counterpart position over a coarse gamma-ray trigger box.
# Both kinds of circular carry coordinates, but the trigger box can be degrees off
# (e.g. a Fermi-GBM localization vs the arcsec MASTER OT position).
_REFINED_POSITION_CUES = re.compile(
    r"optical\s+(?:counterpart|afterglow|transient)|\bOT\b|counterpart|afterglow"
    r"|arcsec|UVOT|XRT\s+position|enhanced\s+XRT|refined\s+(?:position|localization)"
    r"|MASTER\s+OT|discover",
    re.IGNORECASE,
)
_COARSE_POSITION_CUES = re.compile(
    r"\bGBM\b|\bGRM\b|ECLAIRs|real-?time\s+localization|initial\s+localization"
    r"|error\s+(?:radius|circle)\s+of\s+\d|gamma-?ray\s+(?:burst\s+)?(?:localization|detection)",
    re.IGNORECASE,
)


def gather_by_xref(
    seed_id: int,
    fetch: Callable[[int], dict[str, Any] | None],
    max_hops: int = 1,
) -> list[dict[str, Any]]:
    """Collect an event's circular records by BFS over the GCN cross-reference graph.

    `fetch(circular_id)` returns a record ({circularId, subject, body, eventId})
    or None (404). `max_hops` bounds the walk: 1 = the seed plus everything it
    cites (usually the whole flurry). Records are returned in discovery order.
    """
    seen: dict[int, dict[str, Any]] = {}
    frontier = [seed_id]
    hops = 0
    while frontier and hops <= max_hops:
        next_frontier: list[int] = []
        for cid in frontier:
            if cid in seen:
                continue
            record = fetch(cid)
            if record is None:
                continue
            seen[cid] = record
            for xid, _, _ in extract_gcn_xrefs_with_positions(str(record.get("body") or "")):
                if xid not in seen:
                    next_frontier.append(xid)
        frontier = next_frontier
        hops += 1
    return list(seen.values())


def _position_score(record: dict[str, Any]) -> int:
    """+1 if the circular's text reads like a refined/optical position, -1 if coarse."""
    text = f"{record.get('subject', '') or ''}\n{record.get('body', '') or ''}"
    score = 0
    if _REFINED_POSITION_CUES.search(text):
        score += 1
    if _COARSE_POSITION_CUES.search(text):
        score -= 1
    return score


def _record_to_circular(record: dict[str, Any], trigger_time: datetime | None) -> Circular:
    return Circular(
        circular_id=int(record.get("circularId") or 0),
        subject=str(record.get("subject") or ""),
        body=str(record.get("body") or ""),
        event_id=record.get("eventId") or None,
        trigger_time=trigger_time,
    )


def _dedup_key(point: Any) -> tuple[Any, ...]:
    return (point.obj_id, point.filter, point.magsys, round(point.mjd, 5), point.mag)


def aggregate_event(
    records: Iterable[dict[str, Any]],
    extractor: Extractor,
    *,
    trigger_time: datetime | None = None,
    instrument_map: dict[str, int] | None = None,
    bandpass_instrument_map: dict[str, int] | None = None,
    default_instrument_id: int | None = None,
    group_ids: list[int] | None = None,
    event_name: str | list[str] | None = None,
) -> SkyPortalActions:
    """Fuse an event's circulars into one source + a deduped, attributed light curve."""
    group_ids = group_ids or []
    records = list(records)
    extractions = [extractor.extract(_record_to_circular(r, trigger_time)) for r in records]

    # Position: prefer the refined optical-counterpart position over a coarse
    # trigger box. Rank localization-bearing circulars by text cues; ties keep
    # discovery order. Falls back to the first localization when none score.
    candidates = [
        (_position_score(rec), -i, ext.localization)
        for i, (rec, ext) in enumerate(zip(records, extractions, strict=True))
        if ext.localization is not None
    ]
    localization = max(candidates, key=lambda c: (c[0], c[1]))[2] if candidates else None
    # Event name: caller override, else the first one any circular names.
    name = event_name
    if name is None:
        name = next(
            (e.event.event_name for e in extractions if e.event and e.event.event_name), None
        )

    photometry: list[Any] = []
    comments: list[str] = []
    skipped = 0
    skipped_reasons: list[str] = []
    redshift: tuple[float, float | None] | None = None
    source: SourceUpsert | None = None
    event = Event(event_name=name) if name is not None else None

    # A circular retracting the counterpart retracts the whole event's
    # photometry, not just its own: the rows were reported by the circular it
    # withdraws. Without this the retraction re-posts what it takes back.
    retracted = any(e.retraction for e in extractions)

    for extraction in extractions:
        if event is not None:
            extraction.event = event
        extraction.localization = localization
        actions = to_actions(
            extraction,
            instrument_map=instrument_map,
            bandpass_instrument_map=bandpass_instrument_map,
            default_instrument_id=default_instrument_id,
            group_ids=group_ids,
        )
        # The source is defined by the event name + the aggregated position, NOT
        # by whether any photometry row survives — a named counterpart with a
        # position (but skipped/absent photometry) is still a source. Reuse
        # to_actions' source, which already guards the positionless case.
        if source is None and actions.source is not None:
            source = actions.source
        if not retracted:
            photometry.extend(actions.photometry)
        comments.extend(actions.comments)
        skipped += actions.skipped_rows
        skipped_reasons.extend(actions.skipped_reasons)
        if redshift is None and actions.redshift is not None:
            redshift = actions.redshift

    # Dedup photometry (idempotent re-runs; overlapping reports).
    seen: set[tuple[Any, ...]] = set()
    deduped = []
    for point in photometry:
        key = _dedup_key(point)
        if key not in seen:
            seen.add(key)
            deduped.append(point)

    # Unique comments, order preserved.
    seen_c: set[str] = set()
    uniq_comments: list[str] = []
    for comment in comments:
        if comment not in seen_c:
            seen_c.add(comment)
            uniq_comments.append(comment)

    if retracted:
        withdrawn = [e.circular_id for e in extractions if e.retraction]
        uniq_comments.append(
            "A circular withdraws this counterpart "
            f"({', '.join(f'GCN {c}' for c in withdrawn)}); no photometry posted."
        )

    return SkyPortalActions(
        source=source,
        photometry=deduped,
        redshift=redshift,
        comments=uniq_comments,
        skipped_rows=skipped,
        skipped_reasons=tuple(skipped_reasons),
        extractions=tuple(extractions),
    )
