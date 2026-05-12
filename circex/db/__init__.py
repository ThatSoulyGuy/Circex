"""SQLite + FTS5 schema and upsert pipeline. Ported from sjhend03/GCNMCP."""

from circex.db.connection import get_connection
from circex.db.indexer import ingest_path, parse_circular_id, sha1_text, upsert_circular

__all__ = [
    "get_connection",
    "ingest_path",
    "parse_circular_id",
    "sha1_text",
    "upsert_circular",
]
