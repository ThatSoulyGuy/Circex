"""SQLite-backed extraction store.

Keyed (circular_id, extractor_id, model_id, prompt_version). Indexed by
event_name so `get_*` MCP tools can resolve an event to its extraction without
a full scan.

This is distinct from circex.cache.llm.LLMCache. The LLM cache exists to
minimize *API calls* (keyed by body sha1); this store exists to serve *queries*
(keyed by event name, with extraction provenance).
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path

from circex.schema import CircularExtraction

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS extractions (
    circular_id     INTEGER NOT NULL,
    extractor_id    TEXT    NOT NULL,
    model_id        TEXT    NOT NULL DEFAULT '',
    prompt_version  TEXT    NOT NULL DEFAULT '',
    primary_event   TEXT,
    extraction_json TEXT    NOT NULL,
    created_at      REAL    NOT NULL,
    PRIMARY KEY (circular_id, extractor_id, model_id, prompt_version)
);
CREATE INDEX IF NOT EXISTS idx_extractions_primary_event
    ON extractions(primary_event);
CREATE INDEX IF NOT EXISTS idx_extractions_extractor_id
    ON extractions(extractor_id);
"""


def _primary_event_name(extraction: CircularExtraction) -> str | None:
    if extraction.event is None or extraction.event.event_name is None:
        return None
    if isinstance(extraction.event.event_name, list):
        return extraction.event.event_name[0] if extraction.event.event_name else None
    return extraction.event.event_name


def _normalize_event(name: str | None) -> str | None:
    """Match circex.extract.regex.regex_events.normalize_event semantics."""
    if not name:
        return None
    import re

    return re.sub(r"\s+", "", name).upper()


class ExtractionStore:
    """SQLite-backed extraction persistence. One connection per instance."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        # WAL allows concurrent readers + one writer (typical case: the worker
        # serving queries while `circex index` backfills new rows).
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.executescript(SCHEMA_SQL)

    def close(self) -> None:
        self._conn.close()

    def put(self, extraction: CircularExtraction) -> None:
        meta = extraction.extraction_meta
        self._conn.execute(
            """
            INSERT OR REPLACE INTO extractions
                (circular_id, extractor_id, model_id, prompt_version,
                 primary_event, extraction_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                extraction.circular_id,
                meta.extractor,
                meta.model_id or "",
                meta.prompt_version or "",
                _normalize_event(_primary_event_name(extraction)),
                extraction.model_dump_json(by_alias=True),
                time.time(),
            ),
        )
        self._conn.commit()

    def get(
        self,
        circular_id: int,
        extractor_id: str,
        model_id: str = "",
        prompt_version: str = "",
    ) -> CircularExtraction | None:
        row = self._conn.execute(
            """
            SELECT extraction_json FROM extractions
            WHERE circular_id = ? AND extractor_id = ?
              AND model_id = ? AND prompt_version = ?
            """,
            (circular_id, extractor_id, model_id, prompt_version),
        ).fetchone()
        if row is None:
            return None
        return CircularExtraction.model_validate_json(row["extraction_json"])

    def find_by_event(
        self, event_name: str, extractor_id: str | None = None
    ) -> Iterable[CircularExtraction]:
        """Return all stored extractions whose primary_event matches event_name."""
        normalized = _normalize_event(event_name)
        if normalized is None:
            return []
        if extractor_id is not None:
            rows = self._conn.execute(
                """
                SELECT extraction_json FROM extractions
                WHERE primary_event = ? AND extractor_id = ?
                ORDER BY created_at DESC
                """,
                (normalized, extractor_id),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT extraction_json FROM extractions
                WHERE primary_event = ?
                ORDER BY created_at DESC
                """,
                (normalized,),
            ).fetchall()
        return [CircularExtraction.model_validate_json(r["extraction_json"]) for r in rows]

    def list_circular_ids(self, extractor_id: str | None = None) -> list[int]:
        """Return circular IDs that have at least one extraction stored."""
        if extractor_id is None:
            rows = self._conn.execute(
                "SELECT DISTINCT circular_id FROM extractions ORDER BY circular_id"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT DISTINCT circular_id FROM extractions WHERE extractor_id = ? "
                "ORDER BY circular_id",
                (extractor_id,),
            ).fetchall()
        return [int(r["circular_id"]) for r in rows]

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM extractions").fetchone()
        return int(row["n"]) if row else 0

    def __enter__(self) -> ExtractionStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- helpers ----

    def to_jsonl(self) -> str:
        """Dump all rows as JSONL for debugging."""
        rows = self._conn.execute(
            "SELECT circular_id, extractor_id, extraction_json FROM extractions"
        ).fetchall()
        return "\n".join(
            json.dumps(
                {
                    "circular_id": r["circular_id"],
                    "extractor_id": r["extractor_id"],
                    "extraction": json.loads(r["extraction_json"]),
                }
            )
            for r in rows
        )
