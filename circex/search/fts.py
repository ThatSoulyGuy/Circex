"""FTS5 search with event-aware ranking. Ported from sjhend03/GCNMCP src/search.py."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from circex.db.connection import get_connection
from circex.extract.regex.regex_events import extract_event_from_query, normalize_event

_STOPWORDS: frozenset[str] = frozenset(
    {"for", "the", "and", "with", "from", "into", "that", "this", "reports"}
)


def row_to_result(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a SQLite row into a plain dict for search results."""
    return {
        "circular_id": row["circular_id_raw"],
        "primary_event": row["primary_event_raw"],
        "primary_event_norm": row["primary_event_norm"],
        "subject": row["subject"],
        "created_on": row["created_on"],
        "extraction_source": row["extraction_source"],
        "snippet": row["snippet"],
        "score": row["score"],
    }


def parse_fts_terms(query: str) -> str:
    """Tokenize a query into an FTS5 AND-joined term string."""
    terms = re.findall(r"[A-Za-z0-9_+.\-]+", query.lower())
    filtered = [term for term in terms if len(term) > 1 and term not in _STOPWORDS]
    if not filtered:
        return '""'
    return " AND ".join(filtered)


def remove_event_from_query(query: str, event: str | None) -> str:
    """Strip the event token from a free-text query so FTS uses descriptive terms only."""
    if not event:
        return query

    event_no_space = re.escape(event.replace(" ", ""))
    event_with_optional_space = re.escape(event).replace(r"\ ", r"\s*")

    pattern = rf"\b(?:{event_with_optional_space}|{event_no_space})\b"
    cleaned = re.sub(pattern, " ", query, flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def search_circulars(
    db_path: str | Path,
    query: str = "",
    event: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search circulars by keyword, optionally filtered by event.

    Ranking: 3 = primary event match, 2 = secondary event match, 1 = text-only match.
    """
    connection = get_connection(db_path)

    inferred_event = extract_event_from_query(query or "")
    event_norm = normalize_event(event) if event else inferred_event
    keyword_query = remove_event_from_query(query or "", event or inferred_event)

    params: list[Any]
    if keyword_query:
        sql = """
        SELECT DISTINCT
            c.circular_id_raw,
            c.primary_event_raw,
            c.primary_event_norm,
            c.subject,
            c.created_on,
            c.extraction_source,
            snippet(circulars_fts, 1, '[', ']', ' ... ', 18) AS snippet,
            CASE
                WHEN c.primary_event_norm = ? THEN 3
                WHEN e.event_norm = ? THEN 2
                ELSE 1
            END AS score
        FROM circulars_fts
        JOIN circulars c ON circulars_fts.rowid = c.circular_id_int
        LEFT JOIN circular_events e ON e.circular_id_raw = c.circular_id_raw
        WHERE circulars_fts MATCH ?
        """
        params = [event_norm, event_norm, parse_fts_terms(keyword_query)]

        if event_norm:
            sql += " AND (c.primary_event_norm = ? OR e.event_norm = ?)"
            params.extend([event_norm, event_norm])
    else:
        sql = """
        SELECT DISTINCT
            c.circular_id_raw,
            c.primary_event_raw,
            c.primary_event_norm,
            c.subject,
            c.created_on,
            c.extraction_source,
            substr(c.body, 1, 320) AS snippet,
            CASE
                WHEN c.primary_event_norm = ? THEN 3
                WHEN e.event_norm = ? THEN 2
                ELSE 1
            END AS score
        FROM circulars c
        LEFT JOIN circular_events e ON e.circular_id_raw = c.circular_id_raw
        WHERE 1=1
        """
        params = [event_norm, event_norm]

        if event_norm:
            sql += " AND (c.primary_event_norm = ? OR e.event_norm = ?)"
            params.extend([event_norm, event_norm])

    sql += " ORDER BY score DESC, c.created_on DESC, c.circular_id_raw DESC LIMIT ?"
    params.append(limit)

    rows = connection.execute(sql, params).fetchall()
    connection.close()

    return [row_to_result(row) for row in rows]


def get_event_circulars(
    db_path: str | Path,
    event: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return circulars associated with one specific event."""
    return search_circulars(db_path=db_path, query="", event=event, limit=limit)


def get_circular(db_path: str | Path, circular_id: int) -> dict[str, Any] | None:
    """Fetch one circular by its integer ID."""
    connection = get_connection(db_path)

    row = connection.execute(
        """
        SELECT
            c.circular_id_raw,
            c.primary_event_raw,
            c.primary_event_norm,
            c.subject,
            c.created_on,
            c.extraction_source,
            c.body AS snippet,
            0 AS score
        FROM circulars c
        WHERE c.circular_id_int = ?
        """,
        (circular_id,),
    ).fetchone()

    connection.close()

    return row_to_result(row) if row else None
