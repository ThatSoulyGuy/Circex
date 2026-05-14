# Circex

**LLM-based structured extractor for GCN optical astronomy circulars.**

Turns the free text of ~18,600 GCN optical observation reports into validated
JSON conforming to [`nasa-gcn/gcn-schema`](https://github.com/nasa-gcn/gcn-schema).
Three extraction engines (regex baseline, Anthropic Claude, local Ollama) all
implement the same `Extractor` protocol. An MCP-style server lets SkyPortal or
any tool query the extracted data.

```
                    ┌──────────────────────────────────────┐
                    │      Tool clients (SkyPortal,        │
                    │      MCP Inspector, your script)     │
                    └──────────────┬───────────────────────┘
                                   │ MCP (TS bridge) OR direct TCP
                                   ▼
┌─────────────────────────────────────────────────────────────┐
│   circex serve  ────  asyncio TCP worker on :8765           │
│   ────────────────────────────────────────────────────────  │
│   7 tools  ◀──  Extraction store (SQLite, WAL)              │
│   regex / Claude / Ollama extractors (Extractor protocol)   │
└──────────────┬──────────────────────────────────────────────┘
               │ on cache-miss: extract on demand
               ▼
   archive_2025/<circular_id>.json   (40,506 raw circulars)
```

See [`GCN_Optical_Extraction_Plan.pdf`](GCN_Optical_Extraction_Plan.pdf) for the
full design.

---

## Pick your path

| You want to... | Jump to |
|---|---|
| Get one circular's structured JSON, right now | [Recipe A](#recipe-a--extract-one-circular) |
| Batch-extract many circulars to files | [Recipe B](#recipe-b--batch-extract-many-circulars) |
| Compare regex vs Vidushi's published Mistral-7B numbers | [Recipe C](#recipe-c--eval-extractors-against-gold) |
| Use Claude (Haiku or Sonnet) instead of regex | [Recipe D](#recipe-d--use-claude-instead-of-regex) |
| Use Ollama (open-source) | [Recipe D2](#recipe-d2--use-ollama-mistral-7b) |
| Run as an MCP server for another tool to query | [Recipe E](#recipe-e--run-as-an-mcp-server) |
| Ask natural-language questions ("what's the redshift of GRB X?") | [Recipe F](#recipe-f--natural-language-demo) |
| Hand-label circulars for the gold set | [Recipe G](#recipe-g--hand-label-circulars) |
| Install from scratch on a fresh machine | [Installation](#installation) |

---

## Quickstart (60 seconds, no API key)

Assumes the repo is cloned, the four reference repos are in `references/`, and
the archive tarball is at `references/circulars-nlp-paper/data/archive_2025.json.tar.gz`.
See [Installation](#installation) otherwise.

```powershell
# Activate the venv
.\.venv\Scripts\Activate.ps1

# (One-time) Untar the archive + build a stratified subset
circex subset-build --max-optical 50000 --per-stratum 100

# Extract 50 circulars with the regex baseline
circex extract --extractor regex --circulars data/labels/hand_v1 --out runs/regex_v1

# Look at one
Get-Content runs/regex_v1/000216.extraction.json
```

That last command prints structured JSON for GCN circular #216 — GRB 990123,
the gravitationally lensed burst. Event name, photometry rows, redshift, GCN
cross-references, all extracted from prose by the regex baseline.

---

# Recipes

## Recipe A — Extract one circular

The fastest way to feel what the tool does. Start a long-running worker once,
then query any of the 40,506 circulars in the archive.

```powershell
# Shell 1 — leave this running
circex serve --extractor regex --port 8765 --store data/extractions.sqlite
```

```powershell
# Shell 2 — query any circular ID
python demo/cli_client.py --tool extract_properties --args '{\"circular_id\": 21505}'
```

Output: the full `CircularExtraction` JSON for GCN #21505 (one of the
AT2017gfo / GW170817 optical-counterpart circulars).

Try other IDs: `200`, `12345`, `33123` (GRB 230307A), `40000`. The first call
extracts on demand and caches; second call returns instantly.

**Narrower questions** (read straight from the store):

```powershell
python demo/cli_client.py --tool get_redshift       --args '{\"event\":\"GRB 990123\"}'
python demo/cli_client.py --tool get_photometry     --args '{\"event\":\"GRB 990123\"}'
python demo/cli_client.py --tool get_classification --args '{\"event\":\"GRB 990123\"}'
```

**Example output** for `get_redshift` on GRB 990123:

```json
{
  "redshift": 1.61,
  "redshift_measure": "spectroscopic",
  "redshift_type": "absorption"
}
```

## Recipe B — Batch-extract many circulars

Produces one `<id>.extraction.json` per circular in the output directory.

```powershell
# The 50 stratified circulars
circex extract --extractor regex --circulars data/labels/hand_v1 --out runs/regex_50

# A larger custom set — build a 500-circular subset then extract
circex subset-build --max-optical 50000 --per-stratum 100 --out data/subsets/big.json
circex extract --extractor regex --circulars data/subsets/big.json --out runs/regex_500
```

Each output file is a complete `CircularExtraction` matching the Pydantic
schema in `circex/schema/`.

**Validate the outputs**:

```powershell
# If you treat any of these as candidate labels, use:
circex label-validate runs/regex_50
```

## Recipe C — Eval extractors against gold

Runs an extractor over a gold set and writes a markdown report with per-field
P/R/F1, Δ-vs-Vidushi, cost/latency, and a failure-case browser.

**Against Vidushi's published 13,593-row eval set** (regex-only is free):

```powershell
circex eval --extractors regex --gold vidushi --max-circulars 500 --report reports/eval_regex.md
```

Open `reports/eval_regex.md`. Headline:

| Field | regex F1 | Vidushi Mistral-7B F1 | Δ |
|---|---|---|---|
| event.event_name (GRB#) | 0.869 | 0.849 | **+0.020** |
| redshift.redshift | 0.858 | 0.690 | **+0.168** |

Regex already beats her published numbers on both fields with usable gold
support. With Claude added (next recipe), the gap should widen.

**Against your own hand-labels** (once `data/labels/hand_v1/*.label.json` are
filled in — see [Recipe G](#recipe-g--hand-label-circulars)):

```powershell
circex eval --extractors regex --gold data/labels/hand_v1 --report reports/eval_hand.md
```

## Recipe D — Use Claude instead of regex

Same commands as Recipes A–C, swap `--extractor regex` for `--extractor claude-haiku`
or `--extractor claude-sonnet`.

```powershell
# One-time
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# Batch extract 50 circulars (~$0.05 total with Haiku)
circex extract --extractor claude-haiku --circulars data/labels/hand_v1 --out runs/claude_haiku

# Eval Claude alongside regex (~$0.30 for 100 rows with Haiku)
circex eval --extractors regex,claude-haiku --gold vidushi --max-circulars 100 --report reports/eval_haiku.md

# Use Claude as the worker's default extractor
circex serve --extractor claude-haiku --port 8765 --store data/extractions.sqlite
```

**Cost notes**:
- Haiku 4.5: ~$0.001 / circular. Backfilling all 18,642 optical circulars: ~$20.
- Sonnet 4.6: ~$0.005 / circular. Same backfill: ~$95.
- Anthropic prompt caching is enabled (system block + few-shots are cached
  per 5-minute TTL), reducing real cost by ~30-50%.
- LLM cache (SQLite) reuses identical body × prompt-version × model results
  across runs — `circex eval` reruns are free.

## Recipe D2 — Use Ollama (Mistral-7B)

One-time:

```powershell
# Install Ollama (https://ollama.com), then:
ollama pull mistral:7b-instruct-v0.2     # ~4 GB
ollama serve                              # leave running
```

Then:

```powershell
circex extract --extractor ollama --circulars data/labels/hand_v1 --out runs/ollama_v1
```

Same shape as Claude but cost = $0 and latency depends on local hardware.
This is the apples-to-apples comparison to Vidushi/Sharma 2025 (she used the
same model).

## Recipe E — Run as an MCP server

The Python worker speaks a JSON-line protocol on a local TCP port. Any
language with a TCP client can call it; the included TS LeanMCP bridge
(stub in [`leanmcp_bridge/`](leanmcp_bridge/)) translates that to MCP so
SkyPortal can consume.

**Boot the worker:**

```powershell
circex serve --extractor regex --port 8765 --store data/extractions.sqlite
```

**The 7 tools** the worker exposes:

| Tool | Arguments | Returns |
|---|---|---|
| `extract_properties` | `{circular_id: int}` | full `CircularExtraction` |
| `get_redshift` | `{event: str}` | `Redshift` or `null` |
| `get_photometry` | `{event: str}` | `list[PhotometryExt]` |
| `get_classification` | `{event: str}` | `Classification` or `null` |
| `find_counterparts` | `{gw_event_id: str}` | `list[FollowUp]` |
| `search_gcn_circulars` | `{query: str, event?: str, limit?: int}` | FTS5 hits |
| `fetch_gcn_circulars` | `{circular_ids: list[int]}` | raw archive records |

**Call from any language** — here's a raw socket example in PowerShell:

```powershell
$client = New-Object System.Net.Sockets.TcpClient("127.0.0.1", 8765)
$stream = $client.GetStream()
$writer = New-Object System.IO.StreamWriter($stream)
$reader = New-Object System.IO.StreamReader($stream)
$writer.WriteLine('{"tool":"get_redshift","arguments":{"event":"GRB 990123"}}')
$writer.Flush()
$reader.ReadLine()
$client.Close()
```

Python clients can use `demo/cli_client.py` as a reference; it's ~30 lines of
`socket.create_connection` + JSON.

**Pre-populate the store** (so `get_*` queries don't trigger extractions):

```powershell
# Stop the worker first (Ctrl+C), then:
circex index --circulars data/subsets/big.json --extractor regex --store data/extractions.sqlite
# Restart serve.
```

The store is SQLite with WAL mode — you can also keep the worker running and
`circex index` will write concurrently.

## Recipe F — Natural-language demo

The most "demo-able" path. Requires:
- The worker running (Recipe E)
- `$ANTHROPIC_API_KEY` set
- Some extractions already in the store (Recipe A or E backfill)

```powershell
python demo/cli_client.py --question "what's the redshift of GRB 990123?"
```

Claude reads your question, picks `get_redshift` from the tool catalog, calls
the worker, and answers in prose:

> The redshift of GRB 990123 is z = 1.61, measured spectroscopically from
> absorption lines.

Multi-tool questions work too:

```powershell
python demo/cli_client.py --question "what photometry do we have for GRB 990123, and what's the classification?"
```

## Recipe G — Hand-label circulars

Producing the gold set for the full-fidelity eval. 50 source files are already
staged in `data/labels/hand_v1/`.

```powershell
# Open the source for one circular
notepad data/labels/hand_v1/000216.source.md

# Fill in the matching label.json per docs/labeling_spec.md
notepad data/labels/hand_v1/000216.label.json

# Validate (catches schema errors, not correctness)
circex label-validate data/labels/hand_v1
```

The labeling spec at [`docs/labeling_spec.md`](docs/labeling_spec.md) defines
the rules per field. As you label, append discovered schema gaps to the
"Known gaps" section. After ~10 labels, run the eval against your gold:

```powershell
circex eval --extractors regex,claude-haiku --gold data/labels/hand_v1 --report reports/eval_hand.md
```

---

# Reference

## Output schema

Every extractor produces a `CircularExtraction` Pydantic model:

```python
class CircularExtraction(BaseModel):
    circular_id: int
    event: Event | None                  # event_name (str or list), instrument trigger IDs
    follow_up: FollowUp | None           # GCN cross-refs, counterpart-of relations
    localization: Localization | None    # RA/Dec (decimal deg, ICRS J2000)
    datetime_: DateTime | None           # trigger time, observation start/stop
    time_offsets: list[TimeOffset]       # literal "T+234s" captures
    photometry: list[PhotometryExt]      # one row per (filter, epoch)
    spectroscopy: SpectralLines | None   # identified emission/absorption lines
    classification: Classification | None # canonical taxonomy class
    redshift: Redshift | None            # z, error, measure, type
    reporter: Reporter | None            # alerting mission/instrument
    extraction_meta: ExtractionMeta      # model, tokens, cost, latency, cache_hit
```

JSON Schema artifacts for the upstream `nasa-gcn/gcn-schema` PR are dumped to
`schemas/` via `circex schema-dump`.

## Project layout

```
circex/
├── schema/        # Pydantic models mirroring gcn-schema + 2 new schemas
├── extract/
│   ├── protocol.py — Extractor protocol + Circular input
│   ├── regex/     # regex baseline (events, coords, mag tables, redshift, classification, dates)
│   └── llm/       # Claude + Ollama extractors, prompt template, chunker
├── eval/          # four-way evaluation harness
├── server/        # long-lived TCP worker + 7 MCP tool implementations
├── cache/         # SQLite-backed LLM cache
├── data/          # corpus loaders (archive, topic-filter, swift-gold, subset)
├── db/            # SQLite + FTS5 schema + indexer (ported from sjhend03/GCNMCP)
├── fetch/         # GCN HTTP poller (ported)
├── search/        # FTS5 search (ported)
└── taxonomy.py    # time-domain-taxonomy YAML loader

demo/cli_client.py   # standalone tool client + Claude-orchestrated NL demo
leanmcp_bridge/      # TS LeanMCP shim (stub — see leanmcp_bridge/README.md)
schemas/             # JSON Schema artifacts for upstream PR
docs/                # labeling spec, prompt deltas, known issues, runbooks
reports/             # eval + cost-projection outputs
tests/               # 282 tests; pytest tests/ -q
references/          # 4 upstream repos, gitignored
```

## CLI command reference

| Command | What it does |
|---|---|
| `circex extract` | Run one extractor over a circular set, write JSON files |
| `circex eval` | Run extractors against gold, produce a markdown report |
| `circex serve` | Boot the long-lived TCP worker for the 7 MCP tools |
| `circex index --backfill` | Walk a circular set, extract, persist to the SQLite store |
| `circex fetch` | Poll gcn.nasa.gov for new circulars |
| `circex subset-build` | Build a stratified iteration subset from the optical pool |
| `circex schema-dump` | Dump Pydantic models to JSON Schemas (upstream PR artifacts) |
| `circex label-validate` | Validate hand-labeled JSON files against the schema |
| `circex version` | Print the installed version |

All commands accept `--help`.

## The 7 MCP tools (see Recipe E for usage)

See the table in [Recipe E](#recipe-e--run-as-an-mcp-server).

---

## Installation

### Prerequisites

- Python 3.13+ (Python 3.14 supported; CPython on Windows tested)
- Git
- ~30 GB free disk for the archive + reference repos
- Optional: Anthropic API key (Recipe D)
- Optional: Ollama (Recipe D2)
- Optional: Node 20+ for the TS bridge (Recipe E with full MCP shim)

### Fresh setup

```powershell
# 1. Clone
git clone <this repo> Circex
cd Circex

# 2. Create + activate venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install
pip install -e ".[dev]"

# 4. Clone the four reference repos (gitignored; read-only context)
git clone --depth 1 https://github.com/sjhend03/GCNMCP                       references/GCNMCP
git clone --depth 1 https://github.com/nasa-gcn/gcn-schema                   references/gcn-schema
git clone --depth 1 https://github.com/nasa-gcn/circulars-nlp-paper          references/circulars-nlp-paper
git clone --depth 1 https://github.com/skyportal/timedomain-taxonomy         references/timedomain-taxonomy

# 5. (Optional but recommended) untar the archive + build a subset
circex subset-build --max-optical 50000 --per-stratum 100

# 6. (Optional) configure secrets
Copy-Item .env.example .env
# Edit .env and set ANTHROPIC_API_KEY if you want to use Claude
```

### Why is `tdtax` an optional extra?

The PyPI build of `tdtax` (time-domain-taxonomy) uses `ast.Constant.s` which
was removed in Python 3.14. Circex bypasses the broken package by reading the
YAML files directly from `references/timedomain-taxonomy/tdtax/*.yaml`. You
do **not** need `tdtax` installed; just the `references/` clone.

### Verifying the install

```powershell
pytest -q                          # expect: 282 passed
ruff check .                       # expect: All checks passed!
mypy circex                        # expect: Success: no issues found in 59 source files
circex --help                      # expect: lists the 9 commands above
```

---

## Project status

| Sprint | What landed | Commit |
|---|---|---|
| Sprint 0 | Repo scaffold, ported predecessor Python (db/indexer/search/utils/fetcher), CI | `82bb709` |
| Sprint 1 | All Pydantic schemas, taxonomy loader, ground-truth pipeline, labeling spec | `ed7acf4` |
| Sprint 2 | Regex baseline (6 sub-extractors) + composed `RegexExtractor` + 50 stratified label templates | `a849c45` |
| Sprint 3 | Claude (Haiku/Sonnet, tool-use) + Ollama (Mistral-7B, JSON-mode) extractors, prompt v1, SQLite LLM cache | `c18b3a5` |
| Sprint 4 | Four-way eval harness; regex beats Vidushi by +0.02 / +0.17 F1 on her 2 measurable fields | `92eac45` |
| Sprint 5 | Long-lived TCP worker, 7 MCP tools, ExtractionStore (WAL), demo CLI, TS bridge stub | `e67693e` |

282 tests passing. Ruff + mypy strict clean.

### Known issues and open items

See [`docs/known_issues.md`](docs/known_issues.md) (21 entries across all
sprints with severity, status, and code paths). The major open items:

- **Hand-label the 50 staged templates** (Recipe G). Required for the full ~9-field eval.
- **Live LLM eval columns** — run with `$ANTHROPIC_API_KEY` set (Recipe D).
- **TS LeanMCP bridge** — full port from `references/GCNMCP/leanmcp_bridge/` is
  pending (`npm install` + adapt `mcp/gcn/index.ts`); see
  [`leanmcp_bridge/README.md`](leanmcp_bridge/README.md).
- **Upstream license audit** — fill in [`docs/upstream_licenses.md`](docs/upstream_licenses.md).
- **Lower/upper-bound redshifts** (`z ≤ 1.61`) — schema doesn't model bounds yet.

---

## Architecture pointers

- **The plan**: [`GCN_Optical_Extraction_Plan.pdf`](GCN_Optical_Extraction_Plan.pdf)
  (12 pages — goals, schema mapping, 5-phase work plan, decision log).
- **The sprint execution plan**:
  [`~/.claude/plans/come-up-with-a-unified-hopper.md`](~/.claude/plans/come-up-with-a-unified-hopper.md).
- **Prompt deltas vs Vidushi/Sharma 2025**: [`docs/prompt_deltas.md`](docs/prompt_deltas.md).
- **Consistency-pass runbook (A–F)**: [`docs/consistency_passes_runbook.md`](docs/consistency_passes_runbook.md).

---

## Development

```powershell
pytest -q                          # run all 282 tests
pytest tests/extract/llm -q        # one module
pytest -m live                     # only the live-API tests (off by default)

ruff check .                       # lint
ruff format .                      # auto-format
mypy circex                        # type-check (strict on circex/)

# Regenerate JSON Schema artifacts for the upstream PR
circex schema-dump --out schemas/
```

### Conventions

- Python 3.13+ syntax (`X | None`, not `Optional[X]`)
- `pathlib.Path` everywhere
- Pydantic v2
- `structlog` for logging; no `print` outside CLI command output
- Tests deterministic; live API tests behind `@pytest.mark.live`
- Cache keys include `prompt_version` for clean invalidation
- Cross-platform (Windows-first); CI runs windows + ubuntu

---

## Attribution

Built on patterns from
[sjhend03/GCNMCP](https://github.com/sjhend03/GCNMCP) (MIT). The following
modules were adapted from that repository:

- `circex/db/connection.py` (was `src/db.py`)
- `circex/db/indexer.py` (was `src/indexer.py`)
- `circex/search/fts.py` (was `src/search.py`)
- `circex/extract/regex/regex_events.py` (was `src/utils.py`)
- `circex/fetch/gcn_poller.py` (was `src/fetch_circulars.py`)

Other upstream references (not vendored; read at runtime via
`references/`):

- [nasa-gcn/gcn-schema](https://github.com/nasa-gcn/gcn-schema) — output JSON Schema target. Circex will submit an upstream PR for the `Photometry` extension and the new `SpectralLines` / `Classification` schemas.
- [nasa-gcn/circulars-nlp-paper](https://github.com/nasa-gcn/circulars-nlp-paper) — Sharma et al. 2025: the 40,506-circular archive, topic labels, 13,593-row redshift gold + Vidushi's Mistral-7B baseline predictions.
- [skyportal/timedomain-taxonomy](https://github.com/skyportal/timedomain-taxonomy) — 175-class controlled vocabulary for `Classification`.
- Background paper: Sharma et al. 2025, [arXiv:2511.14858](https://arxiv.org/abs/2511.14858).

## License

MIT. See [`LICENSE`](LICENSE).
