# Consistency Passes — Runbook

The plan defines six consistency passes (A–F). Each runs at specific sprint
boundaries and produces a report under `reports/consistency_pass_<letter>.md`.
This doc is the operating procedure.

| Pass | When | Output |
|------|------|--------|
| A — Schema ↔ Pydantic ↔ Extractor output alignment | End of Sprint 1, 3, 5 | `reports/consistency_pass_a.md` |
| B — Regex ↔ LLM field coverage parity | End of Sprint 3 | `reports/consistency_pass_b.md` |
| C — Eval ↔ ground truth ↔ extractor output alignment | End of Sprint 4 | `reports/consistency_pass_c.md` |
| D — MCP tools ↔ persisted DB columns | End of Sprint 5 | `reports/consistency_pass_d.md` |
| E — Cost projection methodology rigor | End of Sprint 4 | `reports/cost_projection_validation.md` |
| F — Reproducibility audit | End of Sprint 4, 5 | `reports/consistency_pass_f.md` |

## How to run

Each pass has its own `scripts/consistency_pass_<letter>.py` (to be written
as we hit each sprint boundary). Until then, this doc carries the
question/method/failure-mode for each.

### Pass A — Schema ↔ Pydantic ↔ Extractor output

**Question:** Does every field that appears downstream have exactly one
canonical home in the schema layer?

**Method:** Walk every Pydantic model in `circex/schema/`. For each field:
- Does it appear in the upstream JSON Schema or one of the two new schemas?
- Does the regex extractor produce it (or document why not)?
- Does the LLM prompt mention it explicitly with a desired format?
- Does the eval comparator have a tolerance rule for it?

**Failure mode caught:** Adding a field to the prompt without updating the
Pydantic model so it silently drops.

### Pass B — Regex ↔ LLM field coverage parity

**Question:** For every field, do both extractors at least *attempt*
extraction, so the eval is a fair comparison?

**Method:** Table-row check for each `CircularExtraction` field:
- `regex_attempts: bool`
- `llm_attempts: bool`
- `gold_has_data_in_50: bool`

**Failure mode caught:** "LLM wins on a field" only because regex never tried.

### Pass C — Eval ↔ ground truth ↔ extractor output

**Question:** Are the metrics being computed actually well-defined?

**Method:** For each cell in the headline table:
- Ground truth column exists and has ≥ 1 non-null value.
- Extractor output has the same Pydantic type as ground truth.
- Comparator function exists with at least one unit test.

Flag any cell with `n_non_null < 10` as "low statistical power."

**Failure mode caught:** F1=1.0 on a field with 2 data points.

### Pass D — MCP tools ↔ persisted DB columns

**Question:** Can every MCP tool be served from cached data?

**Method:** For each of the 5 extraction tools:
- SQL query against the `extractions` table.
- Fallback when cache miss.
- Latency budget.

Verify the DB schema actually has the columns each tool needs.

**Failure mode caught:** `get_photometry(event)` requires an index on `event`
but only `circular_id` is indexed.

### Pass E — Cost projection methodology

**Question:** Is the projected backfill cost defensible?

**Method:** Re-derive cost from raw tokens on a held-out 10-circular sample
not used in the 100-circular projection. Compare projected vs actual on the
held-out 10. If error > 20%, investigate the long tail.

**Failure mode caught:** Projecting from 100 average-length circulars misses
the 99th-percentile-length outliers that dominate cost.

### Pass F — Reproducibility audit

**Question:** Can anyone re-run the eval and reproduce the headline numbers
within tolerance?

**Method:** Run the full eval pipeline twice on a clean cache. Diff the two
reports. Any field where F1 varies by > 0.01 must be either flagged or
eliminated (temperature=0, fixed seeds, persistent cache).

**Failure mode caught:** A "win" over Vidushi that disappears on rerun.
