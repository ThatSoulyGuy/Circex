"""Aggregate an event's circulars into ONE SkyPortal source.

The single-circular path (`circex post`) posts one bulletin at a time. A real
transient is described across many circulars — a discovery circular carries the
position, follow-ups carry the light curve. `aggregate_event` fuses them:

  - position from the first circular that has one (the discovery circular),
  - photometry unioned across every circular (each point keeps its own source
    circular id in altdata),
  - deduped so a re-run or an overlapping report doesn't double-post,
  - a single redshift if any circular states a valid one.

`gather_by_xref` discovers an event's circulars from a seed by walking the GCN
cross-reference graph the extractor already recovers — no event-search API needed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any

from circex.bot.skyportal_map import SkyPortalActions, SourceUpsert, to_actions
from circex.extract.protocol import Circular, Extractor
from circex.extract.regex.regex_events import extract_gcn_xrefs_with_positions
from circex.schema import Event


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
    default_instrument_id: int | None = None,
    group_ids: list[int] | None = None,
    event_name: str | list[str] | None = None,
) -> SkyPortalActions:
    """Fuse an event's circulars into one source + a deduped, attributed light curve."""
    group_ids = group_ids or []
    extractions = [extractor.extract(_record_to_circular(r, trigger_time)) for r in records]

    # Position: the first circular that has one (the discovery circular).
    localization = next((e.localization for e in extractions if e.localization is not None), None)
    # Event name: caller override, else the first one any circular names.
    name = event_name
    if name is None:
        name = next(
            (e.event.event_name for e in extractions if e.event and e.event.event_name), None
        )

    photometry: list[Any] = []
    comments: list[str] = []
    skipped = 0
    redshift: tuple[float, float | None] | None = None
    event = Event(event_name=name) if name is not None else None

    for extraction in extractions:
        if event is not None:
            extraction.event = event
        extraction.localization = localization
        actions = to_actions(
            extraction,
            instrument_map=instrument_map,
            default_instrument_id=default_instrument_id,
            group_ids=group_ids,
        )
        photometry.extend(actions.photometry)
        comments.extend(actions.comments)
        skipped += actions.skipped_rows
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

    obj_id = deduped[0].obj_id if deduped else None
    source: SourceUpsert | None = None
    if obj_id is not None and localization is not None:
        source = SourceUpsert(
            id=obj_id, ra=localization.ra, dec=localization.dec, group_ids=group_ids
        )

    # Unique comments, order preserved.
    seen_c: set[str] = set()
    uniq_comments: list[str] = []
    for comment in comments:
        if comment not in seen_c:
            seen_c.add(comment)
            uniq_comments.append(comment)

    return SkyPortalActions(
        source=source,
        photometry=deduped,
        redshift=redshift,
        comments=uniq_comments,
        skipped_rows=skipped,
    )
