# Known Issues

Running log of caveats, false-positive/false-negative cases, and schema gaps
surfaced during development. Every "⚠" item from a session goes here — chat
notes are ephemeral; this file is the record.

**Severity legend:** L = low (cosmetic / niche), M = medium (affects accuracy
on a known subset), H = high (blocks a deliverable or contaminates eval).

**Status:** `open` (will need a real fix) | `accepted` (known limitation, no
fix planned in v1) | `resolved` (fixed; kept for history).

---

## Sprint 0 — repo scaffolding

### tdtax PyPI install incompatible with Python 3.14 — **resolved**
**Severity:** M. `tdtax`'s `setup.py` uses the removed `ast.Constant.s`
attribute. Fails `pip install` on Py 3.14.
**Workaround:** `circex/taxonomy.py` reads YAML files directly from
`references/timedomain-taxonomy/tdtax/*.yaml`. `tdtax` is now an optional
`[taxonomy]` extra (kept for future use).
**Where:** `pyproject.toml` (extras), `circex/taxonomy.py`.

---

## Sprint 1 — schemas + ground truth

### Topic CSV has malformed circular IDs (e.g., `-4.0`) — **accepted**
**Severity:** L. The first row of
`tables/topic-modeling-tables/observation_based_topics.csv` has a synthetic
`-4.0` record. Defensively skipped in `_coerce_circular_id`.
**Where:** `circex/data/topics.py`.

### Upstream license audit incomplete — **open**
**Severity:** H (blocks any future redistribution claim). The four reference
repos' actual LICENSE files have not been read; `docs/upstream_licenses.md`
contains TODOs. Needs human to open each LICENSE and verify compatibility with
Circex's MIT license.
**Where:** `docs/upstream_licenses.md`.

### Lower/upper-bound redshifts stored as point values — **resolved (v1 convention)**
**Severity:** M (was). Real circulars write `z ≤ 1.61`, `z ≥ 0.2`, `z ~ 0.3`.
The `Redshift` schema only models a point value + symmetric/asymmetric error.
**Resolution (v1, agreed with ICARE):** the extractor sets `redshift: None`
and appends the literal phrase to `ExtractionMeta.notes` as
`"redshift_bound: <phrase>"`, with a `"_redshift_bound"` provenance entry
pointing at the source span. Downstream consumers (SkyPortal, ICARE) read
notes and render the bound as a comment rather than a structured value.
The regex side is wired via `parse_redshift_bound`
(`circex/extract/regex/redshift.py`) and `RegexExtractor`
(`circex/extract/regex/extractor.py`). The LLM prompt should follow the
same convention.
**Schema-level fix deferred to v2:** add
`redshift_bound: Literal["upper","lower","point"] | None` to
`Redshift` so the bound has a typed home. Tracked for the next upstream
gcn-schema PR.
**First surfaced:** circular 216 (GRB 990123, "z =< 1.61").
**Where:** `circex/schema/extraction_meta.py` (`notes` field),
`circex/extract/regex/redshift.py` (`parse_redshift_bound`),
`docs/labeling_spec.md`.

### Initial 5k-ID pool was pre-2017 — **resolved**
**Severity:** M. Stratification on the first 5000 optical IDs gave only 1
GW/neutrino counterpart and 6 spec_z circulars because GW170817 (the first
optical GW counterpart) is circular ~21500+. **Fixed in Sprint 2** by
re-running on the full ~19.6k optical pool — now 100 per stratum (96 for
spec_z).

---

## Sprint 2 — regex baseline

### Classification matches first taxonomy alias, no context — **accepted**
**Severity:** M (intentional — PDF says regex should visibly fail on in-prose
classification).
The matcher returns the first taxonomy alias in body order, regardless of
context. So:
- Every "GRB " circular gets `classification = "GRB"` (taxonomy contains GRB
  as a class) — tautological.
- Circular 14 (GRB 971214 OT) got `classification = "Mira"` (false positive
  via stray alias match).
**Decision:** keep. This is exactly the "regex fails on in-prose
classification" failure mode the eval will quantify. **Do not over-engineer.**
**Where:** `circex/extract/regex/classification.py`.

### Single-mag parser rejects mag < 5 (and z-band mag < 10) — **accepted**
**Severity:** L. The disambiguator that prevents `z = 1.61` (redshift) being
parsed as Sloan-z mag also rejects:
- Filter z magnitudes 5–10 (vanishingly rare in real circulars).
- Any filter magnitude < 5 (e.g., extremely bright nearby reference stars).
**Trade-off chosen:** false-negative on ultra-bright stars over the much more
common false-positive on redshift mentions.
**Where:** `circex/extract/regex/mag_table.py` (`_plausible_mag`).

### Mag-error parser misses `+/-`, `+-` notation — **open**
**Severity:** L. `_DETECTION_RE` accepts `±` or single `+` / `-` only. Many
older circulars (e.g., 216 from 1999) write `R ~ 21.5 +- 0.5` (literal
plus-minus). The mag is captured; the error is dropped.
**Fix:** extend the error pattern to `(?:±|\+/?-|\+-|\+\s*/\s*-)`.
**First surfaced:** circular 216.
**Where:** `circex/extract/regex/mag_table.py`.

### Mag-table parser requires explicit header keywords — **accepted (PDF-intended)**
**Severity:** H on coverage (intentional). Tables without a header line
containing 2+ of {date, mjd, epoch, filter, band, mag, magnitude, err, error,
exp, exptime, exposure} return zero rows. Many real circulars present mag
tables without that header (e.g., a bare 3-column row block).
**Decision:** keep the conservative behavior — the eval will report low recall
on irregular tables, which is the headline regex-vs-LLM failure mode the PDF
calls out.
**Where:** `circex/extract/regex/mag_table.py` (`_looks_like_header`).

### Coords parser requires "RA"/"Dec" labels — **accepted**
**Severity:** M. Many circulars write `(J2000) 12h34m56.7s -23d45m12.3s`
without RA/Dec labels. `_PAIR_RE` requires `RA\s*[=:]?` then a value, then
`Dec`. Unlabelled coord pairs are missed.
**Decision:** keep for v1. The LLM extractor handles this naturally; document
as a known regex gap.
**Where:** `circex/extract/regex/coords.py`.

### TimeOffset sign duplicated in value AND reference — **open**
**Severity:** L. For `T-30s`, the parser sets `value=-30` AND `reference="T-"`.
A consumer doing arithmetic uses `value`; a consumer reading literal phrasing
uses `reference`. If someone manually constructs `TimeOffset(value=+30,
reference="T-")` semantics are undefined.
**Fix candidate:** store unsigned `value` + the sign exclusively in `reference`,
OR document the redundancy invariant in the schema.
**Where:** `circex/schema/time_offset.py`, `circex/extract/regex/dates.py`.

---

## Sprint 3 — LLM extractors

### Claude pricing constants may be stale — **open**
**Severity:** M (affects Sprint 4 cost projection accuracy). `_PRICING` in
`circex/extract/llm/claude.py` has hardcoded USD-per-million-token prices
sourced manually 2026-05-13 (Haiku 4.5: $1/$5; Sonnet 4.6: $3/$15; cache-write
1.25× / cache-read 0.10× input). Anthropic doesn't expose a pricing API; these
constants drift over time.
**Decision:** verify and update before publishing `reports/cost_projection.md`
at Sprint 4 close. Add a one-line check against the docs at that time.
**Where:** `circex/extract/llm/claude.py`.

### Live claude/ollama smoke test deferred to user run — **open**
**Severity:** L. Sprint 3 commit ran 28 mocked tests against ClaudeExtractor +
OllamaExtractor + cache. Full end-to-end against the live Anthropic API was
deferred because `ANTHROPIC_API_KEY` isn't sourced in the shell I'm operating
in.
**How to verify:** `$env:ANTHROPIC_API_KEY="..."; circex extract --extractor
claude-haiku --circulars data/labels/hand_v1 --out runs/claude_haiku_v1` —
expected to produce 50 valid extraction files for ~$0.05 total.
**Where:** N/A (user action).

### Ollama JSON-mode repair retry covers only first failure — **resolved (with caveats)**
**Severity:** L. If the repair retry ALSO produces invalid JSON or a
schema-violating object, the extractor used to re-raise and crash the eval
run. Sprint 6 (Ollama-eval session) hit this on ~5–10% of dense circulars
and made the extractor fail-soft: on a second failure, log a warning and
return an empty extraction so the eval scores it as null-output (which is
the right F1 signal — model failure, not pipeline failure).
**Where:** `circex/extract/llm/ollama.py` (`extract` try/except around
`_call_with_repair`).

---

## Sprint 4 — eval harness

### Vidushi CSV uses "No Information" as null sentinel — **resolved**
**Severity:** M. `redshift_accuracy.csv` "Actual" and "Predicted" telescope /
GRB-number / redshift-type columns store "No Information" for missing values,
not empty strings. Untreated, this fired hundreds of spurious value-mismatch
errors in the comparator.
**Fix:** `_NULL_SENTINELS` in `circex/data/swift_gold.py` now includes
"no information", "n/a", "na", "-" alongside nan/none/null.

### Vidushi gold doesn't cover redshift_type — **accepted**
**Severity:** L. All 500 sampled rows have `Actual Redshift Type` =
"No Information". Comparator correctly reports 0 gold support on
`redshift.redshift_type`. The plan's "four Vidushi fields" turns out to be
three in practice — the Swift catalog doesn't populate type.
**Decision:** Hand-labeled 50 will be the gold source for redshift_type.
**Where:** `references/circulars-nlp-paper/.../redshift_accuracy.csv`.

### Vidushi telescope_name F1 = 0.098 — **flagged for investigation**
**Severity:** L (regex/Claude can't lose to this). Vidushi's predicted telescope
names match the Swift-gold telescope names only ~9.8% of the time. Likely cause:
Swift catalog uses formal codes ("VLT/X-shooter"), Vidushi's pipeline extracts
informal mentions ("the VLT"). Sprint 4 LLM extractors should normalize.

### Live LLM eval columns deferred (no API key in shell) — **open**
**Severity:** L. `reports/eval_v1.md` contains regex-v1 + vidushi-mistral only.
**How to run:** `$env:ANTHROPIC_API_KEY="..."; circex eval --extractors
regex,claude-haiku,claude-sonnet --gold vidushi --max-circulars 100`. Projected
~$0.30 (Haiku) and ~$1 (Sonnet) for 100 rows.

### Photometry/coords/time_offsets contaminate Vidushi-mode eval — **accepted**
**Severity:** L. Vidushi gold only covers 4 fields. The comparator still scores
the other ~7 fields, all gold-null → preds-FP. Failure browser is noisy but the
headline F1 numbers are fine.
**Decision:** acceptable; Sprint 4's hand-labeled-50 eval mode will populate all
fields properly.

### Mismatch semantics: MM = 1 FP + 1 FN — **resolved**
**Severity:** L. Initial `_compare_scalar` emitted `FP` only on value mismatch.
Standard IE convention double-counts (the model both hallucinated AND missed).
Added `MM` outcome; aggregator increments both fp and fn for MM rows.
**Where:** `circex/eval/metrics.py`.

---

## Sprint 5 — MCP server + worker

### ExtractionStore concurrent-access required WAL mode — **resolved**
**Severity:** M. Initial store opened SQLite in default rollback-journal mode.
Running `circex index` while a `circex serve` worker held an open read
connection to the same file crashed the worker (silent connection close, no
log entry).
**Fix:** `PRAGMA journal_mode=WAL` + `synchronous=NORMAL` at connection open.
WAL allows multiple readers + one writer.
**Where:** `circex/server/store.py`.

### TS LeanMCP bridge is a stub — **resolved**
**Severity:** M (was). Sprint 6 completed the bridge: `main.ts` boots a
streamable-HTTP MCP server on :3001, `mcp/gcn/index.ts` declares a
`GcnService` class with `@Tool`-decorated methods for all 7 tools, and
`mcp/gcn/input_schema.ts` carries decorated input classes whose schemas
are auto-generated at boot via `classToJsonSchemaWithConstraints`. End-to-end
flow verified: `tools/list` returns all 7 tools with correct
`properties`/`required`/types; `tools/call` with no Python worker running
returns a clean MCP error frame rather than crashing.
**Load-bearing gotcha:** `tsconfig.json` must set
`useDefineForClassFields: true`; otherwise declared-but-not-assigned class
fields don't materialize on the runtime instance and the schema generator
emits empty `properties: {}` for every tool. Documented in
`leanmcp_bridge/README.md`.
**Pinned versions corrected:** package.json originally listed
`@leanmcp/{core,cli}` at `0.5.0` (which doesn't exist on npm); now pinned
to `^0.4.7` (core, current latest) and `^0.5.12` (cli).

### Demo CLI's call_tool reads first newline only — **accepted**
**Severity:** L. `demo/cli_client.py` accumulates bytes until the first `\n`
and treats that as the full response. For pathologically large responses that
cross many TCP packets without a newline, this would deadlock; in practice the
worker emits one JSON line then awaits the next request.
**Decision:** acceptable for v1; document.
**Where:** `demo/cli_client.py`.

### `find_counterparts` indexes by primary event only — **open**
**Severity:** L. The store indexes each extraction by its FIRST event_name.
Counterparts whose event_name lists the GW ID as the SECOND name (e.g.,
`["AT2017gfo", "GW170817"]`) won't be found by `find_counterparts("GW170817")`.
**Fix candidate:** add a many-to-one event_name → circular_id index table, OR
normalize the event_name list and store all entries.
**Where:** `circex/server/store.py` (`_primary_event_name`).

---

## Sprint 6 — provenance + LeanMCP completion + Ollama eval pilot

### Ollama default model tag `mistral:7b-instruct-v0.2` not pullable — **resolved**
**Severity:** H (was — would crash every Ollama run on a clean install).
The bare `mistral:7b-instruct-v0.2` is not a pullable tag in the Ollama
registry; only quantizations are (`-fp16`, `-q2` … `-q8`, `-q4_K_M`, etc.).
The previous `DEFAULT_OLLAMA_MODEL` produced 404s on every call.
**Fix:** default changed to `mistral:7b-instruct-v0.2-q4_K_M` (the standard
balanced choice, ~4 GB, near-FP16 quality on the eval), with
`CIRCEX_OLLAMA_MODEL` env override for users who want a different
quantization (e.g., `-fp16` for closest-to-S25 fidelity on machines with
enough VRAM).
**Where:** `circex/extract/llm/ollama.py` (`DEFAULT_OLLAMA_MODEL`).

### Mistral-7B produces schema-non-conforming JSON in three patterns — **resolved (with sanitizer)**
**Severity:** H (was — extractions failed on ~30% of dense circulars).
Across the 50-row Ollama eval pilot, Mistral-7B regularly produced JSON
that parsed cleanly but tripped strict Pydantic validation in three specific
ways:

1. Malformed provenance entries — `{"start": 0, "end": 69}` missing the
   `snippet` field, or `provenance.<key>: null` where the schema requires
   a `Span` dict.
2. The `{"X": {"X": null}}` shape on optional nested objects — the model
   includes the parent shape with all-null leaves instead of setting the
   parent to `null`.
3. `follow_up.reference.gcn_circulars` arriving as a list of dicts
   `[{"event_name": "..."}, ...]` instead of the comma-joined string the
   schema requires.

Additionally, the model emits classification values that aren't canonical
class names (e.g., `"HLTG"`) — these fail the `Classification` model's
custom validator.

**Fix:** `OllamaExtractor._sanitize_payload` (new) runs before strict
validation and:
- drops provenance entries that can't form a valid `Span`, recomputing
  the snippet from `body[start:end]` when the model omits or corrupts it;
- collapses `{"X": {"X": null}}` to `"X": null`;
- coerces `follow_up.reference.gcn_circulars` list-of-anything to a
  comma-joined string;
- normalizes classification aliases through `normalize_classification`,
  dropping the field to null when no canonical mapping exists.

The repair retry still fires on schema breaks the sanitizer can't fix
(genuine type errors, etc.), so the comparator-quality F1 signal is
preserved.

**Where:** `circex/extract/llm/ollama.py` (`_sanitize_payload`,
`_parse_validate`).

### Mistral-7B latency on Apple Silicon — **accepted**
**Severity:** L (operational note). The 50-row Ollama eval pilot measured
p50 = 29.5 s/circular, p95 = 215.6 s/circular on an M-series Mac with
Q4_K_M weights. The long-tail is the repair retry firing on circulars
where the first attempt fails validation. Total wall-clock for the 50-row
pilot was ~55 minutes (~66 s/circular average). At that rate a full
500-row eval projects to **~9 hours**, not the ~40 minutes initially
quoted (which extrapolated from the fastest few smoke-test circulars).
**Decision:** Apple Silicon is too slow for the full 500-row eval; queued
for the user's bigger desktop. Handoff details in `~/.claude/projects/.../memory/handoff_ollama_500_row_eval.md`.
**Where:** N/A (hardware bottleneck).

### Mac Homebrew `ollama` formula is missing `llama-server` — **accepted (documented)**
**Severity:** L (one-time install gotcha). On macOS the
`brew install ollama` formula ships a CLI client but not the
`llama-server` runtime binary; the daemon then errors with
`llama-server binary not found` on every generate. The correct install on
Mac is `brew install --cask ollama-app` (or download the Mac app directly
from ollama.com), which bundles the binary at
`/Applications/Ollama.app/Contents/Resources/llama-server`. Linux and
Windows installers are complete out of the box.
**Where:** documented in `README.md` Recipe D2 and in
`leanmcp_bridge/README.md`. Not a code issue.

### Sparse gold in first ~50 rows of `redshift_accuracy.csv` — **accepted**
**Severity:** L (eval methodology). The first 50 rows of the
13,593-row Swift-validated gold set happened to hit a region where only
2/50 had populated event-name and redshift gold (vs. ~400/500 and ~383/500
respectively in the full 500-row sample documented in the writeup). The
50-row Ollama pilot is therefore useful as a smoke test but the F1
numbers (n=2 support) are not publishable.
**Decision:** the headline four-way comparison must come from the 500-row
run (or larger). The 50-row pilot is committed-but-flagged as preliminary.
**Where:** `reports/eval_50_regex_ollama.md`.

---

## Schema / labeling-spec gaps surfaced

(These are open issues the hand-labeling exercise is expected to uncover more
of. Update `docs/labeling_spec.md` "Known gaps" section in parallel.)

- **No per-row photometry epoch** (ICARE P0 #2) — `PhotometryExt` has no
  per-row observation time, but SkyPortal photometry requires an `mjd` per
  point. Design for an `obs_mjd` field (caller-supplied T0, absolute-UT-first
  resolution, null when unresolvable) is written up in
  [`docs/design_obs_mjd.md`](design_obs_mjd.md); code deferred pending sign-off
  on field type and caching strategy.
- **Bound redshifts** (`z ≤ 1.61`) — see above.
- **Conditional/hypothetical fields:** circular 216 reasons about a *putative*
  host galaxy at z ~ 0.2-0.3 conditional on a lensing hypothesis. Our schema
  doesn't model probability/conditional measurements.
- **"Comparable to" magnitude phrasings:** "the OT is comparable in brightness
  to a nearby star at V=18.2" — schema captures `V=18.2` but not the
  comparison relation.

---

## Process / non-code

### Solo-labeler drift risk — **open (mitigation defined)**
**Severity:** M. With one labeler, calibration drifts across the 50-row
labeling session. **Mitigation per plan:** re-label 10 random circulars from
Sprint 1 batch at end of Sprint 2 and compute self-kappa. If low, revise spec
and re-label.
**Where:** `docs/labeling_spec.md` (workflow section), `scripts/label_inter_rater.py`
(to be written).
