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


# A photometry point is "already present" if the source already has a point in the
# same filter within this many days of it. Tolerant on purpose: the same stacked
# observation gets reported at its start / mid / end epoch across circulars (a few
# to tens of minutes apart), and an exact-mjd key would treat those as new points
# and duplicate them. ~0.02 d = ~29 min covers that without merging genuinely
# distinct measurements of a transient in one band. No mag in the key: SkyPortal
# converts magsys->AB on ingest, so the stored mag differs from the posted one.
_DEDUP_MJD_TOL = 0.02

# Session memory: (obj_id, filter) -> mjds already present/posted.
SeenPhotometry = dict[tuple[str, str], list[float]]


def _is_duplicate(seen: SeenPhotometry, point: Any, tol: float = _DEDUP_MJD_TOL) -> bool:
    mjds = seen.get((point.obj_id, point.filter))
    return mjds is not None and any(abs(m - point.mjd) <= tol for m in mjds)


def _remember(seen: SeenPhotometry, obj_id: str, filter_name: str, mjd: float) -> None:
    seen.setdefault((obj_id, filter_name), []).append(mjd)


def process_circular(
    record: dict[str, Any],
    *,
    extractor: Extractor,
    poster: SkyPortalPoster,
    fetch: Callable[[int], dict[str, Any] | None],
    group_ids: list[int],
    instrument_map: dict[str, int] | None = None,
    default_instrument_id: int | None = None,
    seen: SeenPhotometry | None = None,
    prime: Callable[[str], Iterable[tuple[str, str, float]]] | None = None,
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
            for oid, filter_name, mjd in prime(obj_id):
                _remember(seen, oid, filter_name, mjd)
            primed.add(obj_id)
        fresh = []
        for point in actions.photometry:
            if _is_duplicate(seen, point):
                continue
            fresh.append(point)
            _remember(seen, point.obj_id, point.filter, point.mjd)
        skipped = len(actions.photometry) - len(fresh)
        actions = replace(actions, photometry=fresh)

    # Suppress the aggregate's informational note-comments on the live feed — they
    # are not deduplicated and would repeat on every circular of the event. The
    # provenance survives in each photometry point's altdata.
    actions = replace(actions, comments=[])
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
    prime: Callable[[str], Iterable[tuple[str, str, float]]] | None = None,
    on_result: Callable[[ProcessResult], None] | None = None,
) -> list[ProcessResult]:
    """Drive the consumer over a stream of circulars with session idempotency."""
    seen: SeenPhotometry = {}
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
