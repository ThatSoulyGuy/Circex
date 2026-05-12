# Circex

LLM-based extractor for GCN (Gamma-ray Coordinates Network) optical circulars.
Turns the free text of ~18,600 optical observation reports into structured JSON
conforming to [`nasa-gcn/gcn-schema`](https://github.com/nasa-gcn/gcn-schema),
with a serious regex baseline for comparison, exposed via an MCP server SkyPortal
can consume.

See `GCN_Optical_Extraction_Plan.pdf` for the full project plan.

## Attribution

Built on patterns from [sjhend03/GCNMCP](https://github.com/sjhend03/GCNMCP).
Search, indexer, db, event-regex, and GCN fetcher modules adapted from that
repository under its original license.

## Quickstart

```bash
# from the .venv
pip install -e ".[dev]"

# verify
circex --help
pytest
ruff check .
mypy circex
```

## Project layout

```
circex/
├── schema/        # Pydantic models mirroring gcn-schema + new SpectralLines, Classification
├── extract/
│   ├── regex/     # regex baseline (events, coords, mag tables, redshift, classification)
│   └── llm/       # Claude + Ollama extractors with structured output
├── eval/          # four-way evaluation harness
├── server/        # long-lived Python worker for the MCP server
├── cache/         # SQLite-backed LLM result cache
├── data/          # corpus loaders (archive, topic-filter, swift-gold)
├── db/            # SQLite schema + indexer (ported)
├── fetch/         # GCN poller (ported)
└── search/        # FTS5 search (ported)
```

## Reference repos

These live under `references/` (gitignored). They are read-only context:

- `references/GCNMCP/` — predecessor; reusable Python files were ported (not forked).
- `references/gcn-schema/` — output JSON Schema target.
- `references/circulars-nlp-paper/` — Sharma et al. 2025: corpus, topic labels, redshift gold + Vidushi baseline.
- `references/timedomain-taxonomy/` — controlled vocab for `Classification`.

## License

MIT. See `LICENSE`.
