"""Where circulars come from: the live GCN Kafka stream, or a replay directory.

Both yield the same record shape ({circularId, subject, body, eventId}) so the
processor is source-agnostic — the replay source makes the whole pipeline
testable without Kafka credentials or the network.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any


def replay_dir_records(directory: Path) -> Iterator[dict[str, Any]]:
    """Yield circular records from `{directory}/*.json` in id order (replay a flurry)."""
    paths = sorted(directory.glob("*.json"), key=lambda p: int(p.stem) if p.stem.isdigit() else 0)
    for path in paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        if "circularId" in record:
            yield record


def dir_fetch(directory: Path) -> Callable[[int], dict[str, Any] | None]:
    """A fetch(circular_id) that reads bodies from a local directory (for replay)."""

    def fetch(circular_id: int) -> dict[str, Any] | None:
        path = directory / f"{circular_id}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    return fetch


def gcn_kafka_records(
    client_id: str,
    client_secret: str,
    *,
    topic: str = "gcn.circulars",
) -> Iterator[dict[str, Any]]:
    """Yield circulars live from the GCN Kafka stream (production path).

    Requires GCN client credentials (https://gcn.nasa.gov/quickstart) and the
    optional `gcn-kafka` dependency. Imported lazily so the rest of the package
    has no hard Kafka dependency.
    """
    from gcn_kafka import Consumer

    consumer = Consumer(client_id=client_id, client_secret=client_secret)
    consumer.subscribe([topic])
    while True:
        for message in consumer.consume(timeout=1):
            if message.error():
                continue
            value = message.value()
            if value is not None:
                yield json.loads(value)
