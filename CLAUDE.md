# Circex — Claude guidance

This file is loaded into Claude's context automatically each session.

## What this project is

LLM-based extractor for GCN optical circulars, with a serious regex baseline
and an MCP server. Full spec: `GCN_Optical_Extraction_Plan.pdf`. Working plan:
`C:\Users\bkmcm\.claude\plans\come-up-with-a-unified-hopper.md`.

End goal: structured JSON conforming to `nasa-gcn/gcn-schema`, four-way eval
(regex / Ollama / Claude-Haiku / Claude-Sonnet) vs Vidushi/Sharma 2025 baseline,
MCP tools SkyPortal can call.

## Repo layout (target)

- `circex/` — main Python package (Python 3.13+, Pydantic v2)
- `references/` — **read-only** clones of four upstream repos (gitignored). Do not modify.
- `schemas/` — JSON Schema artifacts dumped from Pydantic for upstream PR.
- `data/` — gitignored runtime data (untarred archive, labels, subsets).
- `docs/` — labeling spec, prompt deltas, license audit, consistency-pass runbook.
- `reports/` — eval and cost-projection markdown outputs.
- `leanmcp_bridge/` — Sprint 5 TS layer.

## Dev commands (run from repo root with `.venv` active)

```
pytest                  # tests
ruff check .            # lint
ruff format .           # format
mypy circex             # type check (strict on circex/)
circex --help           # CLI
```

## Conventions

- Python 3.13+ syntax (`X | None`, not `Optional[X]`).
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
