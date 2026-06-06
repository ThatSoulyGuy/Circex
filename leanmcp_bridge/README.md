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
        │  (MCP over streamable HTTP)
        ▼
leanmcp_bridge/  (this folder, Node + TypeScript)
   main.ts                — boots LeanMCP HTTP server on :3001
   mcp/gcn/index.ts       — GcnService class declaring the 9 Circex tools
   mcp/gcn/input_schema.ts — decorated input dataclasses → JSON Schema
   bridge/python_bridge.ts — TCP client; falls back to subprocess on legacy
        │  (JSON-line protocol over TCP localhost:8765)
        ▼
circex serve --worker  (Python, asyncio)
   circex/server/worker.py        — the actual JSON-line server
   circex/server/tools.py         — the 9 tool implementations
   circex/server/store.py         — SQLite ExtractionStore
```

## The 9 tools

| Tool | Args | Returns |
|---|---|---|
| `extract_properties` | `{circular_id: int}` | full `CircularExtraction` (archive lookup) |
| `extract_text` | `{body: str, circular_id?: int, subject?: str, event_id?: str}` | full `CircularExtraction` (live path) |
| `get_redshift` | `{event: str}` | `Redshift \| null` |
| `get_photometry` | `{event: str}` | `list[PhotometryExt]` |
| `get_classification` | `{event: str}` | `Classification \| null` |
| `find_counterparts` | `{gw_event_id: str}` | `list[FollowUp]` |
| `search_by_position` | `{ra: float, dec: float, radius_arcsec: float, limit?: int}` | `list[ConeHit]` |
| `search_gcn_circulars` | `{query: str, event?: str, limit?: int}` | `list[SearchHit]` |
| `fetch_gcn_circulars` | `{circular_ids: list[int]}` | `list[Circular]` |

`extract_text` is the live-pipeline entry point — it extracts from a raw
body without an archive lookup, for circulars delivered over gcn.circulars
(Kafka) that aren't archived yet. `search_by_position` is the position-based
join for un-named optical transients: a cone search over stored
`localization` returning `{circular_id, event_name, ra, dec,
separation_arcsec}` sorted by separation.

## Quickstart

```bash
# 1. Start the Python worker on :8765
circex serve --host 127.0.0.1 --port 8765 --store data/extractions.sqlite

# 2. In another shell, install bridge deps and boot the TS server
cd leanmcp_bridge/
npm install
npm run dev   # listens on :3001

# 3. Point an MCP client at http://localhost:3001/mcp
```

Verify the bridge is up and the 9 tools are registered:

```bash
curl -s http://localhost:3001/health
# -> {"status":"ok","mode":"stateless",...}

curl -sS -X POST http://localhost:3001/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# -> {"result":{"tools":[{"name":"extract_properties",...},...]}}
```

If the Python worker isn't running, tool calls return a structured MCP error
with `isError: true` and a message that names the missing
`circex serve` process — they don't crash the bridge.

## How the schema generation works

Each input class in `mcp/gcn/input_schema.ts` uses TypeScript decorators
(`@SchemaConstraint`, `@Optional`) to declare per-field constraints, and
LeanMCP's `classToJsonSchemaWithConstraints` reflects the TypeScript types at
boot to build the JSON Schema served by `tools/list`. Two `tsconfig.json`
flags are load-bearing:

- `experimentalDecorators` + `emitDecoratorMetadata` — turn on the legacy
  decorator semantics LeanMCP's `@Tool` and `@SchemaConstraint` rely on.
- `useDefineForClassFields: true` — without this, `circular_id!: number`
  declarations don't materialize on the runtime instance, and the schema
  generator (which loops over `Object.keys(instance)`) sees nothing and
  emits an empty `properties: {}` for every tool.

## Environment variables

| Var | Default | Purpose |
|---|---|---|
| `PORT` | `3001` | HTTP port for the LeanMCP server |
| `CIRCEX_WORKER_HOST` | `127.0.0.1` | Python worker hostname |
| `CIRCEX_WORKER_PORT` | `8765` | Python worker TCP port |
| `CIRCEX_WORKER_TIMEOUT_MS` | `30000` | Per-call socket timeout |
| `CIRCEX_LEGACY_PY_BRIDGE` | unset | When `1`, falls back to predecessor's subprocess model (currently raises a not-implemented error; port from `references/GCNMCP/leanmcp_bridge/` if needed for debugging) |

## Scripts

| Command | Effect |
|---|---|
| `npm run dev` | Boot the server via `tsx` (no build step, hot-friendly) |
| `npm run start` | Same as `dev` |
| `npm run typecheck` | `tsc --noEmit` against the full source |
| `npm run build` | `tsc` → `dist/` |
| `npm test` | Node test runner (placeholder; see TODO below) |

## TODO

- Tests: no `tests/` directory yet. The Python worker tests in
  `tests/server/` cover the JSON-line protocol; this bridge needs its own
  unit tests against a mocked TCP server.
- The legacy subprocess fallback (`CIRCEX_LEGACY_PY_BRIDGE=1`) currently
  raises a not-implemented error. If you need it for debugging on a box
  where the worker can't run as a persistent process, port `py_bridge.py`
  from `references/GCNMCP/leanmcp_bridge/`.

## Why not the Python MCP SDK?

The advisor confirmed keeping the TypeScript LeanMCP layer for consistency
with the gcn.nasa.gov stack. The Python `mcp` SDK would let us merge the
bridge into the worker, but at the cost of diverging from the gcn-side
deployment model.
