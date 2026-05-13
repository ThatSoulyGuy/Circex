"""SQLite-backed LLM response cache.

Keyed on (extractor_id, model_id, prompt_version, circular_id, sha1(body)).
Stores the full CircularExtraction JSON plus token/cost/latency telemetry.
Bumping prompt_version invalidates cleanly: old entries are simply not hit;
no migration required.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from circex.schema import CircularExtraction

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS llm_cache (
    extractor_id    TEXT    NOT NULL,
    model_id        TEXT    NOT NULL,
    prompt_version  TEXT    NOT NULL,
    circular_id     INTEGER NOT NULL,
    body_sha1       TEXT    NOT NULL,
    response_json   TEXT    NOT NULL,
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    cost_usd        REAL,
    latency_ms      REAL,
    created_at      REAL    NOT NULL,
    PRIMARY KEY (extractor_id, model_id, prompt_version, circular_id, body_sha1)
);
CREATE INDEX IF NOT EXISTS idx_llm_cache_circular_id ON llm_cache(circular_id);
"""


def cache_key(body: str) -> str:
    """sha1 of the circular body. Stable across runs; part of the cache key."""
    return hashlib.sha1(body.encode("utf-8", errors="ignore")).hexdigest()


@dataclass(frozen=True)
class CachedExtraction:
    extraction: CircularExtraction
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None
    latency_ms: float | None


class LLMCache:
    """SQLite-backed cache. One file, one connection per instance."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA_SQL)

    def close(self) -> None:
        self._conn.close()

    def get(
        self,
        extractor_id: str,
        model_id: str,
        prompt_version: str,
        circular_id: int,
        body_sha1: str,
    ) -> CachedExtraction | None:
        row = self._conn.execute(
            """
            SELECT response_json, tokens_in, tokens_out, cost_usd, latency_ms
            FROM llm_cache
            WHERE extractor_id = ? AND model_id = ? AND prompt_version = ?
              AND circular_id = ? AND body_sha1 = ?
            """,
            (extractor_id, model_id, prompt_version, circular_id, body_sha1),
        ).fetchone()
        if row is None:
            return None
        return CachedExtraction(
            extraction=CircularExtraction.model_validate_json(row["response_json"]),
            tokens_in=row["tokens_in"],
            tokens_out=row["tokens_out"],
            cost_usd=row["cost_usd"],
            latency_ms=row["latency_ms"],
        )

    def put(
        self,
        extractor_id: str,
        model_id: str,
        prompt_version: str,
        circular_id: int,
        body_sha1: str,
        extraction: CircularExtraction,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        cost_usd: float | None = None,
        latency_ms: float | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO llm_cache (
                extractor_id, model_id, prompt_version, circular_id, body_sha1,
                response_json, tokens_in, tokens_out, cost_usd, latency_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                extractor_id,
                model_id,
                prompt_version,
                circular_id,
                body_sha1,
                extraction.model_dump_json(by_alias=True),
                tokens_in,
                tokens_out,
                cost_usd,
                latency_ms,
                time.time(),
            ),
        )
        self._conn.commit()

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM llm_cache").fetchone()
        return int(row["n"]) if row else 0

    def __enter__(self) -> LLMCache:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def cache_key_components(
    extractor_id: str,
    model_id: str,
    prompt_version: str,
    circular_id: int,
    body: str,
) -> dict[str, str | int]:
    """Helper for logging the canonical cache key components."""
    return {
        "extractor_id": extractor_id,
        "model_id": model_id,
        "prompt_version": prompt_version,
        "circular_id": circular_id,
        "body_sha1": cache_key(body),
    }
