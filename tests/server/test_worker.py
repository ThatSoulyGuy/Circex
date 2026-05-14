"""End-to-end TCP socket test for the asyncio worker."""

from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path

import pytest

from circex.schema import (
    CircularExtraction,
    Event,
    ExtractionMeta,
    Redshift,
)
from circex.server.store import ExtractionStore
from circex.server.worker import serve


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def populated_store(tmp_path: Path) -> Path:
    path = tmp_path / "store.sqlite"
    store = ExtractionStore(path)
    store.put(
        CircularExtraction(
            circular_id=1,
            event=Event(event_name="GRB 240101A"),
            redshift=Redshift(redshift=0.5, redshift_type="host"),
            extraction_meta=ExtractionMeta(extractor="regex-v1"),
        )
    )
    store.close()
    return path


@pytest.mark.asyncio
async def test_worker_round_trip(populated_store: Path) -> None:
    port = _free_port()

    server_task = asyncio.create_task(
        serve(store_path=populated_store, host="127.0.0.1", port=port)
    )
    # Give the server a moment to bind.
    await asyncio.sleep(0.2)

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        request = {"tool": "get_redshift", "arguments": {"event": "GRB 240101A"}, "id": "r1"}
        writer.write((json.dumps(request) + "\n").encode("utf-8"))
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=2.0)
        writer.close()
        await writer.wait_closed()

        response = json.loads(line.decode("utf-8"))
        assert response["ok"] is True
        assert response["id"] == "r1"
        assert response["result"]["redshift"] == 0.5
    finally:
        server_task.cancel()
        with __import__("contextlib").suppress(asyncio.CancelledError):
            await server_task


@pytest.mark.asyncio
async def test_worker_returns_error_for_unknown_tool(populated_store: Path) -> None:
    port = _free_port()
    server_task = asyncio.create_task(
        serve(store_path=populated_store, host="127.0.0.1", port=port)
    )
    await asyncio.sleep(0.2)

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        request = {"tool": "nonexistent_tool", "arguments": {}, "id": "r2"}
        writer.write((json.dumps(request) + "\n").encode("utf-8"))
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=2.0)
        writer.close()
        await writer.wait_closed()

        response = json.loads(line.decode("utf-8"))
        assert response["ok"] is False
        assert "unknown tool" in response["error"]
        assert response["id"] == "r2"
    finally:
        server_task.cancel()
        with __import__("contextlib").suppress(asyncio.CancelledError):
            await server_task
