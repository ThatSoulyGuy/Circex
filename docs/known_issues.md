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

### Lower/upper-bound redshifts stored as point values — **open**
**Severity:** M. Real circulars write `z ≤ 1.61`, `z ≥ 0.2`, `z ~ 0.3`. Our
`Redshift` schema only models a point value + symmetric/asymmetric error. A
labeler given `z ≤ 1.61` has to either store `redshift=1.61` (loses the bound
semantics) or leave it null (loses the value).
**Decision needed:** add `redshift_bound: Literal["upper","lower","point"] | None`
to the schema OR define a labeling rule that stores upper-bounds as point with
a flag in `extraction_meta` or notes.
**First surfaced:** circular 216 (GRB 990123, "z =< 1.61").
**Where:** `circex/schema/redshift.py`, `docs/labeling_spec.md`.

### Initial 5k-ID pool was pre-2017 — **resolved**
**Severity:** M. Stratification on the first 5000 optical IDs gave only 1
GW/neutrino counterpart and 6 spec_z circulars because GW170817 (the first
optical GW counterpart) is circular ~21500+. **Fixed in Sprint 2** by
re-running on the full ~19.6k optical pool — now 100 per stratum (96 for
spec_z).

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

### Ollama JSON-mode repair retry covers only first failure — **open**
**Severity:** L. If the repair retry ALSO produces an invalid JSON or a
schema-violating object, `_call_with_repair` re-raises. No second repair.
**Decision:** acceptable for v1; Mistral-7B's JSON mode is usually reliable.
Sprint 4 metrics will surface if this is a real problem.
**Where:** `circex/extract/llm/ollama.py`.

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

## Schema / labeling-spec gaps surfaced

(These are open issues the hand-labeling exercise is expected to uncover more
of. Update `docs/labeling_spec.md` "Known gaps" section in parallel.)

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
