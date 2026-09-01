# Circex — Claude guidance

This file is loaded into Claude's context automatically each session.

## What this project is

LLM-based extractor for GCN optical circulars, with a serious regex baseline
and an MCP server. Full spec: `GCN_Optical_Extraction_Plan.pdf`. Working plan
(Windows dev box): `C:\Users\bkmcm\.claude\plans\come-up-with-a-unified-hopper.md`.

End goal: structured JSON conforming to `nasa-gcn/gcn-schema`, four-way eval
(regex / Ollama / Claude-Haiku / Claude-Sonnet) vs Vidushi/Sharma 2026 baseline,
MCP tools SkyPortal can call.

## Repo layout (target)

- `circex/` — main Python package (Python 3.12+, Pydantic v2)
- `references/` — **read-only** clones of four upstream repos (gitignored). Do not modify.
- `schemas/` — JSON Schema artifacts dumped from Pydantic for upstream PR.
- `data/` — gitignored runtime data (untarred archive, labels, subsets).
- `docs/` — labeling spec, prompt deltas, license audit, consistency-pass runbook.
- `reports/` — eval and cost-projection markdown outputs.
- `leanmcp_bridge/` — TS LeanMCP front-end (`main.ts`, `mcp/gcn/{index,input_schema}.ts`,
  `bridge/python_bridge.ts`). MCP server on :3001, forwards to Python worker on :8765
  over TCP. Node 20+ required; `npm install` then `npm run dev`. No longer a stub.

## Dev commands (run from repo root with `.venv` active)

```
pytest                  # tests
ruff check .            # lint
ruff format .           # format
mypy circex             # type check (strict on circex/)
circex --help           # CLI
```

## Conventions

- Python 3.12+ syntax (`X | None`, not `Optional[X]`). SkyPortal pins `<3.13`,
  so the package must stay installable on 3.12.
- `pathlib.Path` everywhere; no raw string slashes.
- Pydantic v2 (`BaseModel`, `Field`, `model_validate`, `model_dump`).
- `structlog` for logging; never `print` outside CLI command outputs.
- Tests are deterministic; live API tests sit behind `@pytest.mark.live`.
- Cache keys include `prompt_version`; bumping the version invalidates cleanly.
- Cross-platform (Windows-first dev box). CI runs windows + ubuntu matrix.

## Do not

- Modify anything in `references/` — those are read-only upstream clones.
- Commit `data/`, `.venv/`, `.env`, or `*.sqlite`. Gitignored.
- Skip the consistency passes at sprint boundaries (see plan, Pass A–F).
- Hardcode prices or model IDs — pull from config.
- Add scope outside optical observations until Phase 4 acceptance criterion is met.

## Predecessor attribution

Ported from [sjhend03/GCNMCP](https://github.com/sjhend03/GCNMCP):
`db/connection.py`, `db/indexer.py`, `extract/regex/regex_events.py`,
`search/fts.py`, `fetch/gcn_poller.py`.

## Active handoffs

Per-session state, gotchas, and resumption details live as project
memories under `~/.claude/projects/-Users-ericphillips-.../memory/`.
Read those before assuming the codebase is in a clean state — they
capture things that don't survive `git log` (in-flight runs on other
machines, model-tag fixups, environment-specific install steps).
