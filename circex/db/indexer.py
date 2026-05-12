"""SHA1-dedup upsert pipeline. Ported from sjhend03/GCNMCP src/indexer.py."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from circex.db.connection import get_connection
from circex.extract.regex.regex_events import clean_text, extract_events, normalize_event


def sha1_text(text: str) -> str:
    """SHA1 hex digest of input string."""
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def parse_circular_id(value: Any) -> tuple[str | None, int | None]:
    """Normalize a circular ID to (raw_string, integer_or_None)."""
    if value is None:
        return None, None

    if isinstance(value, int):
        return str(value), value

    if isinstance(value, float):
        raw = format(value, "g")
        if value.is_integer():
            return str(int(value)), int(value)
        return raw, None

    text = str(value).strip()
    if not text:
        return None, None

    try:
        dec = Decimal(text)
    except (InvalidOperation, ValueError):
        return text, None

    if dec == dec.to_integral_value():
        return str(int(dec)), int(dec)

    return text, None


def upsert_circular(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    """Insert or update a circular record; idempotent via record_hash."""
    circular_id_raw, circular_id_int = parse_circular_id(record.get("circularId"))
    if circular_id_raw is None:
        raise ValueError("Record is missing circularId")

    subject = clean_text(record.get("subject"))
    body = clean_text(record.get("body"))
    created_on = record.get("createdOn")
    submitter = clean_text(record.get("submitter"))
    fmt = clean_text(record.get("format"))
    raw_event_id = clean_text(record.get("eventId")) or None

    record_hash = sha1_text(json.dumps(record, sort_keys=True, ensure_ascii=False))

    existing = conn.execute(
        "SELECT record_hash FROM circulars WHERE circular_id_raw = ?",
        (circular_id_raw,),
    ).fetchone()

    if existing and existing["record_hash"] == record_hash:
        return

    primary_event_raw, all_events, extraction_source = extract_events(record)
    primary_event_norm = normalize_event(primary_event_raw)

    if primary_event_norm and primary_event_norm not in all_events:
        all_events.insert(0, primary_event_norm)

    conn.execute(
        """
        INSERT INTO circulars (
            circular_id_raw,
            circular_id_int,
            subject,
            body,
            created_on,
            submitter,
            format,
            raw_event_id,
            primary_event_raw,
            primary_event_norm,
            extraction_source,
            llm_confidence,
            record_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(circular_id_raw) DO UPDATE SET
            circular_id_int=excluded.circular_id_int,
            subject=excluded.subject,
            body=excluded.body,
            created_on=excluded.created_on,
            submitter=excluded.submitter,
            format=excluded.format,
            raw_event_id=excluded.raw_event_id,
            primary_event_raw=excluded.primary_event_raw,
            primary_event_norm=excluded.primary_event_norm,
            extraction_source=excluded.extraction_source,
            llm_confidence=excluded.llm_confidence,
            record_hash=excluded.record_hash
        """,
        (
            circular_id_raw,
            circular_id_int,
            subject,
            body,
            created_on,
            submitter,
            fmt,
            raw_event_id,
            primary_event_raw,
            primary_event_norm,
            extraction_source,
            None,
            record_hash,
        ),
    )

    conn.execute("DELETE FROM circular_events WHERE circular_id_raw = ?", (circular_id_raw,))
    for event_norm in all_events:
        conn.execute(
            """
            INSERT OR IGNORE INTO circular_events (circular_id_raw, event_norm, is_primary)
            VALUES (?, ?, ?)
            """,
            (
                circular_id_raw,
                event_norm,
                1 if event_norm == primary_event_norm else 0,
            ),
        )

    conn.execute("DELETE FROM circulars_fts WHERE circular_id_raw = ?", (circular_id_raw,))
    conn.execute(
        """
        INSERT INTO circulars_fts (circular_id_raw, subject, body)
        VALUES (?, ?, ?)
        """,
        (circular_id_raw, subject, body),
    )


def iter_json_records(input_path: str | Path) -> Iterable[dict[str, Any]]:
    """Yield JSON records from a file or directory of .json / .jsonl files."""
    path = Path(input_path)

    if path.is_file():
        suffix = path.suffix.lower()
        if suffix == ".jsonl":
            with path.open("r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if line:
                        yield json.loads(line)
        elif suffix == ".json":
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
                if isinstance(payload, list):
                    yield from payload
                elif isinstance(payload, dict):
                    yield payload
                else:
                    raise ValueError(f"Unsupported JSON payload in {input_path}")
        else:
            raise ValueError(f"Unsupported file type: {path}")

    elif path.is_dir():
        for child in sorted(path.rglob("*.json")):
            with child.open("r", encoding="utf-8") as f:
                yield json.load(f)
        for child in sorted(path.rglob("*.jsonl")):
            with child.open("r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if line:
                        yield json.loads(line)
    else:
        raise FileNotFoundError(input_path)


def ingest_path(db_path: str | Path, input_path: str | Path) -> int:
    """Ingest all JSON records from input_path into the database. Returns count."""
    connection = get_connection(db_path)
    count = 0

    with connection:
        for record in iter_json_records(input_path):
            upsert_circular(connection, record)
            count += 1

    connection.close()
    return count
