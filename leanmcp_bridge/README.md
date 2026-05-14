# Circex TS LeanMCP Bridge

Thin TypeScript layer that speaks MCP to clients (SkyPortal, MCP Inspector, the
Anthropic Computer Use SDK) and forwards calls to the long-lived Python worker
over a local TCP socket.

This replaces the predecessor's per-call subprocess model (one `python` spawn
per tool invocation). The Python worker keeps the Anthropic client, the LLM
cache, the taxonomy load, and the SQLite connections warm across calls.

## Architecture

```
SkyPortal / MCP client
        │  (MCP over stdio or HTTP)
        ▼
leanmcp_bridge/  (this folder, Node + TypeScript)
   main.ts                — boots LeanMCP HTTP server on :3001
   mcp/gcn/index.ts       — declares the 7 Circex tools
   bridge/python_bridge.ts — TCP client; falls back to subprocess on legacy
        │  (JSON-line protocol over TCP localhost:8765)
        ▼
circex serve --worker  (Python, asyncio)
   circex/server/worker.py        — the actual JSON-line server
   circex/server/tools.py         — the 7 tool implementations
   circex/server/store.py         — SQLite ExtractionStore
```

## The 7 tools

| Tool | Args | Returns |
|---|---|---|
| `extract_properties` | `{circular_id: int}` | full `CircularExtraction` |
| `get_redshift` | `{event: str}` | `Redshift \| null` |
| `get_photometry` | `{event: str}` | `list[PhotometryExt]` |
| `get_classification` | `{event: str}` | `Classification \| null` |
| `find_counterparts` | `{gw_event_id: str}` | `list[FollowUp]` |
| `search_gcn_circulars` | `{query: str, event?: str, limit?: int}` | `list[SearchHit]` |
| `fetch_gcn_circulars` | `{circular_ids: list[int]}` | `list[Circular]` |

## Quickstart (deferred — requires `npm install`)

```bash
# 1. Start the Python worker on :8765
circex serve --host 127.0.0.1 --port 8765 --store data/extractions.sqlite

# 2. In another shell, boot the TS bridge
cd leanmcp_bridge/
npm install
npm run dev   # listens on :3001

# 3. Point an MCP client at http://localhost:3001/mcp
```

## TODO: port from the predecessor

Most of the predecessor's `leanmcp_bridge/` directory ports verbatim. The one
file that fundamentally changes is `bridge/python_bridge.ts`: it switches from
spawning `python py_bridge.py` per call to opening a TCP socket on
`localhost:8765` and writing one JSON line per request.

`bridge/python_bridge.ts` in this folder is the new socket-based client.
`mcp/gcn/index.ts`, `mcp/gcn/input_schema.ts`, and `main.ts` should be copied
from `references/GCNMCP/leanmcp_bridge/` and the tool defs rewritten to the
7-tool set above. The predecessor's input-schema patterns are reusable.

Set `LEGACY_PY_BRIDGE=1` in the environment to fall back to the predecessor's
subprocess model for debugging.

## Why not the Python MCP SDK?

The advisor confirmed keeping the TypeScript LeanMCP layer for consistency
with the gcn.nasa.gov stack. The Python `mcp` SDK would let us merge the
bridge into the worker, but at the cost of diverging from the gcn-side
deployment model.
