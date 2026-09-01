# Changelog

## 0.2.0

The grammar-constrained LLM path and the hybrid router — the system the write-up
describes and the one running in production — were never in 0.1.0. This release
publishes them.

### Added

- **`HybridExtractor`** (`circex.extract.hybrid`). Routes each field to whichever
  extractor's failure mode that field tolerates: regex for event identity and
  coordinates, the constrained LLM for photometry, redshift and classification.
- **`LlamaServerExtractor`** (`circex.extract.llm.llama_server`). Grammar-constrained
  decoding against a llama.cpp OpenAI-compatible server, so the sampler cannot emit
  a token that violates the schema. Includes a pruned grammar (72% smaller than the
  full schema), bounded arrays and strings, response caching, and a configurable
  timeout.
- `llm_grammar_schema(require_fields=...)` and `LlamaServerExtractor(require_fields=...)`
  / `CIRCEX_LLAMA_REQUIRE_FIELDS`. Whether the grammar names every field in
  `required` is model-specific: Mistral-7B pads the photometry array with
  fabricated rows when they are required, while Qwen3 returns an empty object when
  they are not. Defaults to off, which is Mistral's behaviour.
- `LlamaServerExtractor(api_key=...)` / `CIRCEX_LLAMA_API_KEY`. Sends a bearer
  token, for a server reached over the internet rather than an ssh tunnel. Omitted
  entirely when unset, so a localhost server is unaffected.
- `SkyPortalActions.extractions` — the extractions a bundle was built from. Callers
  needing a field with no place in the SkyPortal write bundle (event designations,
  classification) no longer have to run the extractor a second time.

### Fixed

- Improved SVOM handling: the coordinate parser now reads both notations SVOM
  circulars use, a combined `R.A., Dec.` label and a split-line
  `R.A. (J2000)` / `Dec. (J2000)` pair.
- The ZTF/GROWTH single-candidate counterpart table is now parsed.
- A source is created from the event name and position rather than from whichever
  photometry rows survive, so a named, positioned counterpart with unpostable
  photometry is still a source.
- `LlamaServerExtractor` no longer caches an extraction produced by a transport
  failure, which would otherwise poison the cache and be silently skipped on re-run.
- Event names now match across prefix whitespace during eval (`GRB971214` ==
  `GRB 971214`).

## 0.1.0

Initial release: regex baseline, Ollama and Claude extractors, the schema, the
eval harness, the MCP-style server, and the SkyPortal ingestion path.
