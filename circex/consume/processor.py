"""Process one incoming circular into SkyPortal — the per-message pipeline.

For each circular: reconstruct its event via the cross-reference graph, aggregate
position + light curve, and post *idempotently* — a session-level `seen` set (and,
live, the source's existing photometry) means re-seeing an event never re-posts a
point. So the same handler is safe to run on every circular as it streams in.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, replace
from typing import Any

from circex.bot import aggregate_event
from circex.bot.aggregate import gather_by_xref
from circex.bot.poster import SkyPortalPoster
from circex.extract.protocol import Extractor


@dataclass
class ProcessResult:
    circular_id: int
    obj_id: str | None
    photometry_posted: int
    photometry_skipped: int  # idempotent skips (already posted)
    status: str  # posted | nothing-postable


def _key(point: Any) -> tuple[Any, ...]:
    # No mag: SkyPortal converts magsys->AB on ingest (stored mag != posted mag),
    # but preserves filter + mjd, so this key survives the round-trip for dedup.
    return (point.obj_id, point.filter, round(point.mjd, 4))


def process_circular(
    record: dict[str, Any],
    *,
    extractor: Extractor,
    poster: SkyPortalPoster,
    fetch: Callable[[int], dict[str, Any] | None],
    group_ids: list[int],
    instrument_map: dict[str, int] | None = None,
    default_instrument_id: int | None = None,
    seen: set[tuple[Any, ...]] | None = None,
    prime: Callable[[str], Iterable[tuple[Any, ...]]] | None = None,
    primed: set[str] | None = None,
) -> ProcessResult:
    """Reconstruct the circular's event, aggregate it, and post the new photometry."""
    circular_id = int(record.get("circularId") or 0)
    records = gather_by_xref(circular_id, fetch, max_hops=1)
    actions = aggregate_event(
        records,
        extractor,
        instrument_map=instrument_map or {},
        default_instrument_id=default_instrument_id,
        group_ids=group_ids,
    )
    if actions.source is None or not (actions.photometry or actions.redshift):
        return ProcessResult(circular_id, None, 0, 0, "nothing-postable")

    obj_id = actions.source.id
    skipped = 0
    if seen is not None:
        # Live idempotency: prime `seen` once per object from SkyPortal's existing
        # photometry so restarts don't re-post; then dedup within the session.
        if prime is not None and primed is not None and obj_id not in primed:
            seen.update(prime(obj_id))
            primed.add(obj_id)
        fresh = [p for p in actions.photometry if _key(p) not in seen]
        skipped = len(actions.photometry) - len(fresh)
        for point in fresh:
            seen.add(_key(point))
        actions = replace(actions, photometry=fresh)

    poster.post(actions)
    return ProcessResult(circular_id, obj_id, len(actions.photometry), skipped, "posted")


def run(
    records: Iterator[dict[str, Any]],
    *,
    extractor: Extractor,
    poster: SkyPortalPoster,
    fetch: Callable[[int], dict[str, Any] | None],
    group_ids: list[int],
    instrument_map: dict[str, int] | None = None,
    default_instrument_id: int | None = None,
    prime: Callable[[str], Iterable[tuple[Any, ...]]] | None = None,
    on_result: Callable[[ProcessResult], None] | None = None,
) -> list[ProcessResult]:
    """Drive the consumer over a stream of circulars with session idempotency."""
    seen: set[tuple[Any, ...]] = set()
    primed: set[str] = set()
    results: list[ProcessResult] = []
    for record in records:
        result = process_circular(
            record,
            extractor=extractor,
            poster=poster,
            fetch=fetch,
            group_ids=group_ids,
            instrument_map=instrument_map,
            default_instrument_id=default_instrument_id,
            seen=seen,
            prime=prime,
            primed=primed,
        )
        results.append(result)
        if on_result is not None:
            on_result(result)
    return results
