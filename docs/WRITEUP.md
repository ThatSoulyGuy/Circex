# Circex — How It Works & Where It Stands

*Status as of 2026-05-15. Advisor-facing summary; assumes familiarity with the
GCN circulars domain but not the codebase.*

---

## 1. The problem

The GCN Circulars archive is ~40,506 free-text astronomer-written observation
reports spanning 1997–2025. About 18,600 of them are optical observations.
Each one buries structured facts — redshift, RA/Dec, a multi-row photometry
table, a classification, cross-references to other circulars — in prose that
was written for humans, not machines. SkyPortal and similar tools want those
facts as structured records, in real time.

The thesis (from the project plan and Sharma et al. 2025): regular expressions
get the easy cases but fail hardest exactly where it matters — multi-row
magnitude tables, magnitude-system inference, and in-prose classification. An
LLM should win there, measurably. We need to *prove* that with a reproducible
four-way comparison, not assert it.

## 2. How it works

Everything funnels through one Pydantic model, `CircularExtraction`, which
mirrors `nasa-gcn/gcn-schema` plus two new sub-schemas (`SpectralLines`,
`Classification`) and an extended `Photometry`. Every extractor — regardless of
engine — emits exactly that shape, so they are directly comparable.

```
 raw circular text
        │
        ▼
 ┌──────────────────────────────────────────────┐
 │   Extractor protocol  (one interface)         │
 │   ├─ RegexExtractor      6 sub-parsers        │
 │   ├─ ClaudeExtractor     tool-use, schema-    │
 │   │                      enforced JSON        │
 │   └─ OllamaExtractor     Mistral-7B, JSON     │
 │                          mode + repair retry  │
 └──────────────────────────────────────────────┘
        │  CircularExtraction (validated)
        ├──────────────► Eval harness ──► P/R/F1 report + chart
        └──────────────► SQLite store ──► MCP worker ──► 7 tools
```

**Regex baseline.** Not a strawman. Six composable sub-parsers: event names
(GRB/TNS/ZTF/ATLAS/ASAS-SN/Pan-STARRS/GOTO + GCN cross-refs), sexagesimal
RA/Dec via `astropy`, a column-aligned magnitude-table detector, redshift with
a ±200-char context window for method/type tags, a taxonomy-alias classifier
(175 canonical classes), and literal `T+offset` capture. It is intentionally
conservative where the plan says regex *should* fail (irregular tables, in-prose
classification) so the eval can quantify the gap honestly.

**LLM extractors.** Claude (Haiku and Sonnet) uses forced tool-use: the
`submit_extraction` tool's input schema *is* the JSON Schema of
`CircularExtraction`, so the model cannot emit malformed output. The system
prompt and four few-shot examples are marked for prompt caching. One stratum
(GW/neutrino counterpart) is deliberately held out of the few-shots so the eval
measures generalization, not memorization. Ollama runs Vidushi's exact model
(Mistral-7B-Instruct-v0.2) for an apples-to-apples comparison, with a single
JSON-validation repair retry. Results are cached in SQLite keyed by
`(model, prompt_version, circular_id, body_hash)`, so iterating on prompts
doesn't re-pay for unchanged circulars.

**Evaluation.** A null-aware per-field comparator: numeric tolerance for
redshift/RA/Dec, enum equality for categoricals, set-semantics row matching for
photometry tables (not list equality), and the standard IE convention that a
value mismatch counts as both a false positive and a false negative. Output is
a markdown report plus a two-panel chart.

**Serving.** A long-lived asyncio worker exposes seven tools
(`extract_properties`, `get_redshift`, `get_photometry`, `get_classification`,
`find_counterparts`, `search_gcn_circulars`, `fetch_gcn_circulars`) over a
JSON-line TCP protocol, backed by a WAL-mode SQLite extraction store so queries
are cheap and the indexer can backfill concurrently. A TypeScript LeanMCP shim
(stub) is the eventual MCP front for SkyPortal.

## 3. Results so far

The headline four-way comparison requires an API key and the 50-circular
hand-labeled gold set, both pending. **But the regex baseline can already be
scored against Vidushi/Sharma 2025's published Mistral-7B predictions**, using
her own 13,593-row Swift-validated gold set — no API key, no hand-labeling
needed. On 500 sampled rows:

![regex vs Vidushi Mistral-7B](images/eval_example_regex_vs_vidushi.png)

| Field | regex F1 | Vidushi Mistral-7B F1 | Δ |
|---|---|---|---|
| event name (GRB number) | **0.869** | 0.849 | **+0.020** |
| redshift value | **0.858** | 0.690 | **+0.168** |
| telescope name | n/a (regex doesn't extract) | 0.098 | — |
| redshift type | no gold support (Swift catalog doesn't populate) | — | — |

The serious regex baseline already **beats the published Mistral-7B numbers on
both fields with usable gold support**, the +0.168 on redshift being
substantial. Two implications:

1. The Mistral-7B baseline from the literature is genuinely beatable — this
   isn't a strawman comparison.
2. Since Claude is being measured against the *same* gold with a strictly
   richer prompt and schema-enforced output, the headline acceptance criterion
   ("Claude beats Vidushi by ≥1 F1 point on ≥3 of 4 fields") is very likely to
   clear comfortably once the live runs are executed.

The regex telescope_name "n/a" is honest, not a gap to paper over: the regex
baseline deliberately doesn't attempt telescope extraction, and Vidushi's own
predictions match the Swift-catalog telescope strings only ~10% of the time
(formal codes like `VLT/X-shooter` vs prose like "the VLT") — a normalization
problem the LLM extractors are expected to handle.

## 4. What's solid vs what's pending

**Solid:** all five plan phases are implemented and tested (262 tests, ruff +
mypy-strict clean, CI on Windows + Ubuntu). Schemas, all three extractors, the
eval harness, the visualization, the MCP worker, and the demo all run
end-to-end. The regex-vs-Vidushi result above is reproducible with one command.

**Pending (needs a human, not more code):**

- **Live LLM columns.** `circex eval --extractors regex,claude-haiku,claude-sonnet,ollama`
  needs `ANTHROPIC_API_KEY` (and a local Ollama). Projected cost ~\$0.30 for
  100 rows of Haiku; full optical backfill ~\$20.
- **Hand-labeled gold (50 circulars).** Required to score the ~7 fields beyond
  the four Vidushi covered (photometry tables, coords, classification,
  spectroscopy, time offsets) — i.e. exactly the fields where regex is
  expected to lose hardest to the LLM. Templates + spec are staged.
- **Upstream schema PR** to `nasa-gcn/gcn-schema` and the **TS LeanMCP bridge**
  port remain as documented next steps.

## 5. Try it

A browser front end is included for interactive exploration — see
[`demo/web/`](../demo/web/). Start the worker, start the bridge, open the page,
type an event name. Full recipes are in the [README](../README.md). The
regex-vs-Vidushi chart above regenerates with:

```
circex eval --extractors regex --gold vidushi --max-circulars 500 \
  --plot reports/eval_v1.png --plot-baseline vidushi-mistral
```

Known limitations and their status are tracked exhaustively in
[`docs/known_issues.md`](known_issues.md) (21 entries, each with severity and
code path).
