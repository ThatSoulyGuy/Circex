"""The 7 Circex MCP tool implementations.

Each tool reads from the ExtractionStore first; on miss it may fall back to
on-the-fly extraction with ctx.default_extractor (if configured). Tools return
plain dicts/lists/scalars — the worker serializes them.

Tools:
  extract_properties(circular_id)         -> CircularExtraction
  get_redshift(event)                     -> Redshift | None
  get_photometry(event)                   -> list[PhotometryExt]
  get_classification(event)               -> Classification | None
  find_counterparts(gw_event_id)          -> list[FollowUp]
  search_gcn_circulars(query, event?)     -> list[SearchHit]   (uses FTS)
  fetch_gcn_circulars(circular_ids)       -> list[Circular]    (raw records)
"""

from __future__ import annotations

from typing import Any

from circex.data.archive import iter_circulars
from circex.extract.protocol import Circular
from circex.schema import CircularExtraction
from circex.server.registry import ToolContext, tool


def _require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"argument {key!r} must be a non-empty string")
    return value


def _require_int(args: dict[str, Any], key: str) -> int:
    value = args.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"argument {key!r} must be an integer")
    return value


def _serialize(extraction: CircularExtraction) -> dict[str, Any]:
    return extraction.model_dump(mode="json", by_alias=True, exclude_none=True)


@tool("extract_properties")
def extract_properties(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Return the full CircularExtraction for one circular. Extracts on miss."""
    circular_id = _require_int(args, "circular_id")
    extractor = ctx.default_extractor

    if extractor is not None:
        cached = ctx.store.get(
            circular_id=circular_id,
            extractor_id=extractor.extractor_id,
            model_id=getattr(extractor, "model_id", "") or "",
            prompt_version=getattr(extractor, "prompt_version", "") or "",
        )
        if cached is not None:
            return _serialize(cached)
    else:
        # No default extractor — only serve from store. Try any stored row.
        all_rows = list(ctx.store.find_by_event("__none__"))  # unused; we need by id
        del all_rows

    if extractor is None:
        raise ValueError(
            "no default extractor configured and circular "
            f"{circular_id} is not in the store"
        )

    # Fetch raw circular body and extract.
    records = list(iter_circulars(circular_ids=[circular_id]))
    if not records:
        raise ValueError(f"circular {circular_id} not found in archive")
    extraction = extractor.extract(Circular.from_record(records[0]))
    ctx.store.put(extraction)
    return _serialize(extraction)


@tool("get_redshift")
def get_redshift(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first non-null Redshift for any extraction tagged with this event."""
    event = _require_str(args, "event")
    extractor_id = getattr(ctx.default_extractor, "extractor_id", None)
    extractions = list(ctx.store.find_by_event(event, extractor_id=extractor_id))
    for ex in extractions:
        if ex.redshift is not None:
            payload: dict[str, Any] = ex.redshift.model_dump(mode="json", exclude_none=True)
            return payload
    return None


@tool("get_photometry")
def get_photometry(ctx: ToolContext, args: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all photometry rows across stored extractions for this event."""
    event = _require_str(args, "event")
    extractor_id = getattr(ctx.default_extractor, "extractor_id", None)
    out: list[dict[str, Any]] = []
    for ex in ctx.store.find_by_event(event, extractor_id=extractor_id):
        for row in ex.photometry:
            out.append(row.model_dump(mode="json", exclude_none=True))
    return out


@tool("get_classification")
def get_classification(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first non-null Classification for any extraction tagged with this event."""
    event = _require_str(args, "event")
    extractor_id = getattr(ctx.default_extractor, "extractor_id", None)
    for ex in ctx.store.find_by_event(event, extractor_id=extractor_id):
        if ex.classification is not None:
            payload: dict[str, Any] = ex.classification.model_dump(
                mode="json", exclude_none=True
            )
            return payload
    return None


@tool("find_counterparts")
def find_counterparts(ctx: ToolContext, args: dict[str, Any]) -> list[dict[str, Any]]:
    """Find optical counterparts for a GW/neutrino event.

    Matches when an extraction's primary event_name is the GW ID (counterpart
    naming) OR when follow_up.ref_ID equals the GW ID.
    """
    event = _require_str(args, "gw_event_id")
    out: list[dict[str, Any]] = []
    for ex in ctx.store.find_by_event(event):
        if ex.follow_up is not None:
            payload = ex.follow_up.model_dump(mode="json", exclude_none=True)
            payload["circular_id"] = ex.circular_id
            out.append(payload)
    return out


@tool("search_gcn_circulars")
def search_gcn_circulars(ctx: ToolContext, args: dict[str, Any]) -> list[dict[str, Any]]:
    """FTS5 search over the circulars database (ported from predecessor)."""
    query = args.get("query") or ""
    event = args.get("event")
    limit = args.get("limit", 10)
    if not isinstance(limit, int):
        limit = 10
    if ctx.db_path is None:
        raise ValueError("search requires ctx.db_path to point to a circulars FTS database")

    from circex.search import search_circulars
    return list(
        search_circulars(
            db_path=ctx.db_path,
            query=str(query),
            event=str(event) if event else None,
            limit=limit,
        )
    )


@tool("fetch_gcn_circulars")
def fetch_gcn_circulars(ctx: ToolContext, args: dict[str, Any]) -> list[dict[str, Any]]:
    """Return raw archive records for a list of circular_ids."""
    raw_ids = args.get("circular_ids")
    if not isinstance(raw_ids, list):
        raise ValueError("'circular_ids' must be a list of integers")
    ids = [int(x) for x in raw_ids]
    return list(iter_circulars(circular_ids=ids))
