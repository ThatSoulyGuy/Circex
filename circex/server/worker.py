"""Long-lived asyncio TCP worker for Circex MCP tools.

Listens on localhost:8765 (configurable). One JSON message per line.
Cross-platform (TCP localhost works on Windows, Linux, macOS).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path

import structlog

# Importing tools registers them as a side-effect.
from circex.server import tools as _tools_module  # noqa: F401
from circex.server.protocol import ToolRequest, ToolResponse
from circex.server.registry import ToolContext, dispatch
from circex.server.store import ExtractionStore

log = structlog.get_logger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    ctx: ToolContext,
) -> None:
    peer = writer.get_extra_info("peername")
    log.info("client_connected", peer=peer)
    try:
        while not reader.at_eof():
            line = await reader.readline()
            if not line:
                break
            line_str = line.decode("utf-8", errors="replace").strip()
            if not line_str:
                continue
            response = _handle_request_line(ctx, line_str)
            writer.write((json.dumps(response.to_dict()) + "\n").encode("utf-8"))
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        log.info("client_disconnected", peer=peer)


def _handle_request_line(ctx: ToolContext, line: str) -> ToolResponse:
    """Parse one JSON line + dispatch. Returns a ToolResponse (success or error)."""
    request_id: str | None = None
    try:
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError("request must be a JSON object")
        request = ToolRequest.from_dict(payload)
        request_id = request.id
        result = dispatch(ctx, request.tool, request.arguments)
        return ToolResponse(ok=True, result=result, id=request_id)
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        log.warning("request_failed", error=str(exc))
        return ToolResponse(ok=False, error=str(exc), id=request_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("request_handler_error")
        return ToolResponse(ok=False, error=f"internal error: {exc}", id=request_id)


async def serve(
    store_path: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    db_path: Path | None = None,
    default_extractor: object | None = None,
) -> None:
    """Run the worker server. Blocks until cancelled / shutdown."""
    store = ExtractionStore(store_path)
    ctx = ToolContext(
        store=store,
        default_extractor=default_extractor,
        db_path=str(db_path) if db_path else None,
    )
    log.info("worker_starting", host=host, port=port, store=str(store_path))

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _handle_client(reader, writer, ctx)

    server = await asyncio.start_server(handler, host=host, port=port)
    try:
        async with server:
            log.info("worker_listening", host=host, port=port)
            await server.serve_forever()
    finally:
        store.close()
