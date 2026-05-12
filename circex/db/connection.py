"""SQLite connection + schema. Ported from sjhend03/GCNMCP src/db.py."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS circulars (
    circular_id_raw TEXT PRIMARY KEY,
    circular_id_int INTEGER,
    subject TEXT,
    body TEXT,
    created_on INTEGER,
    submitter TEXT,
    format TEXT,
    raw_event_id TEXT,
    primary_event_raw TEXT,
    primary_event_norm TEXT,
    extraction_source TEXT,
    llm_confidence REAL,
    record_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS circular_events (
    circular_id_raw TEXT NOT NULL,
    event_norm TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    UNIQUE(circular_id_raw, event_norm),
    FOREIGN KEY(circular_id_raw) REFERENCES circulars(circular_id_raw)
);

CREATE INDEX IF NOT EXISTS idx_circulars_circular_id_int
    ON circulars(circular_id_int);

CREATE INDEX IF NOT EXISTS idx_circulars_primary_event_norm
    ON circulars(primary_event_norm);

CREATE INDEX IF NOT EXISTS idx_circular_events_event_norm
    ON circular_events(event_norm);

CREATE INDEX IF NOT EXISTS idx_circulars_created_on
    ON circulars(created_on);

CREATE VIRTUAL TABLE IF NOT EXISTS circulars_fts USING fts5(
    circular_id_raw UNINDEXED,
    subject,
    body
);
"""


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection, configure pragmas, ensure schema exists."""
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA synchronous=NORMAL;")
    connection.execute("PRAGMA temp_store=MEMORY;")
    connection.execute("PRAGMA foreign_keys=ON;")

    connection.executescript(SCHEMA_SQL)
    return connection
