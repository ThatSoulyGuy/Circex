# Circex × ICARE — pipeline update

Slide-ready outline for a **progress update**. Audience already knows what
Circex is; this covers what shipped for the ICARE integration (the P0/P1 asks),
the end-to-end SkyPortal pipeline, and what's left to go live. Every number is
current and reproducible.

---

## Slide 1 — Where we are in one line

> The ICARE ask list is **done**: all 12 items (P0 → P2) shipped, the
> Circex → SkyPortal pipeline runs end-to-end in dry-run, and a real
> 20-circular flurry validated it (and surfaced + fixed three real bugs).

---

## Slide 2 — The ICARE ask list → scorecard

| # | Ask | Status |
|---|---|---|
| **P0 #1** | Extract from a raw body, not just an archived id | ✅ `extract_text` |
| **P0 #2** | Per-row photometry epoch (mjd) | ✅ `obs_mjd` + `obs_time` |
| **P1 #3** | Coordinate / cone-search query path | ✅ `search_by_position` |
| **P1 #4** | Canonical filter / bandpass | ✅ sncosmo `bandpass` + published crosswalk |
| **P1 #5** | Canonical telescope / instrument names | ✅ alias map + `*_canonical` fields |
| **P1 #6** | Explicit detection-vs-upper-limit flag | ✅ `is_detection` |
| **P1 #7** | Per-value provenance in serialized output | ✅ round-trips through `model_dump` |
| P2 #8 | `event_name` carries AT/optical name | ✅ multi-event lists |
| P2 #9 | classification confidence + taxonomy path | ✅ `confidence` + `taxonomy_path` |
| P2 #10 | Versioned, published JSON schema | ✅ semver + CI gate (v0.3.0) |
| P2 #11 | Redshift-bounds representation | ✅ bound → comment, not a scalar |
| P2 #12 | Streaming throughput + idempotency | ✅ body-sha cache keying |

> **12 / 12 shipped**, each on `master`, each CI-green.

## Slide 3 — P0 #1: the live path (`extract_text`)

- **Before:** `extract_properties(circular_id)` looked the id up in the 2025
  archive → fails for live circulars off `gcn.circulars` (Kafka).
- **Now:** `extract_text({body, circular_id?, subject?, event_id?, trigger_time?})`
  extracts from the raw body — no archive lookup.
- Idempotent: the LLM cache keys on `sha1(body)`, so a re-delivered Kafka
  message is served from cache, not re-billed.
- The worker is now **9 tools**, mirrored in the TypeScript MCP bridge.

## Slide 4 — P0 #2: per-row epoch (`obs_mjd` / `obs_time`)

- **The ICARE pain point:** SkyPortal photometry needs an `mjd` per point;
  icarebot was skipping rows it couldn't time.
- Each `PhotometryExt` now carries `obs_mjd` (float MJD, UTC — SkyPortal's
  `mjd`) and `obs_time` (ISO mirror), resolved from:
  - an **absolute UT/MJD** stated in the row, or
  - a caller-supplied **trigger time T0** + the circular's relative offset.
- Null when neither is available — never fabricated. (Design:
  `docs/design_obs_mjd.md`.)

## Slide 5 — P1: the fields that make photometry postable

| Field | What it gives ICARE |
|---|---|
| `bandpass` | sncosmo name (`sdssr`, `bessellr`, `2massj`) — **enumerated crosswalk published** so the mapping is provably complete |
| `telescope_canonical` | `"the VLT"`/`"ESO-VLT"` → `VLT`; seed alias map, extend from ICARE's `instrument_id` table |
| `is_detection` | detection vs upper limit, auto-inferred; `limiting_mag` populated |
| `provenance` | `(start, end, snippet)` per value → lands in SkyPortal `altdata.note` |
| `search_by_position` | cone search over `localization` — the join for **un-named** transients |

## Slide 6 — The pipeline: Circex → SkyPortal

```
gcn.circulars (Kafka) → extract_text → CircularExtraction
                                            │  skyportal_map.to_actions()
                                            ▼
                         {source, photometry[], redshift, comments}
                                            │
                        dry-run (default)   │   --live + token
                                            ▼
                          POST /sources · POST /photometry · PATCH redshift · comments
```

- Refuses to post **timeless** photometry → comments it instead of inventing a
  time.
- Bound redshifts → comment, not a scalar `_redshift`.
- Unmapped telescopes → flagged, never guessed.
- One command: `circex post --from-file <circular.json> --extractor <name>`.

## Slide 7 — Why the live bot needs the LLM (the money slide)

Same circular (the GRB 260604C seed), same bot:

| | regex baseline | Ollama / Mistral-7B |
|---|---|---|
| reads table date → `obs_mjd` | ✗ | ✓ `mjd 61199.83` |
| **postable photometry** | **0** | **1** |

The LLM reads `2026-06-08 20:01:14` and emits a timed point. And the
deterministic filter crosswalk **corrects the LLM's calibration error**
(Mistral mislabeled Cousins `Rc` as `sdssr/ab` → bot posts the correct
`bessellr/vega`).

**Live demo (one command):**
```
circex post --from-file docs/fixtures/grb260604c_44877.json --extractor ollama --group-ids 3
→ POST /sources    {"id":"GRB260604C","group_ids":[3]}
  POST /photometry {"mjd":61199.83,"filter":"bessellr","magsys":"vega",
                    "mag":23.08,"magerr":0.18,"altdata":{"circex_circular_id":44877}}
```

## Slide 8 — Validated on a real flurry (GRB 260604C)

20 circulars, ~14 telescopes, fetched + extracted live.

- **Event graph reconstructs** from one seed: all 20 resolve to one event;
  cross-reference union = 22 circulars.
- **It found 3 real bugs, all fixed (with regression tests):**
  - classification false positives (`"Overtone"` ← author initial `"O"`):
    **9/12 garbage → 0**.
  - a silent table-parser bug dropping `mag_error` on every table.
  - a common single-detection photometry line being missed.
- (Full output: `docs/flurry_test_grb260604c.md`.)

## Slide 9 — Engineering quality / CI

- **417 tests**, `ruff` + `mypy --strict` clean, CI on Ubuntu + Windows.
- CI also typechecks the **TypeScript MCP bridge** and gates **schema drift +
  version bumps** — downstream consumers pin to the schema version (v0.3.0).
- All ICARE work landed as small, individually-CI-green commits.

## Slide 10 — To go live (the asks back to you)

1. **A SkyPortal sandbox + token** to point `circex post --live` at.
2. **A generic GCN `instrument_id`** (and, optionally, ICARE's full
   `telescope→id` table). SkyPortal *requires* an `instrument_id` per
   photometry point; the bot already falls back to a generic one (matching
   ICARE) so it posts everything — the table just upgrades attribution from
   "generic GCN" to the precise instrument. (P1 #5 — the canonical *name* — is
   already done; the id table is ICARE-owned data, not a Circex deliverable.)
3. **Trigger:** wire a GCN Kafka consumer (vs. manual/replay for now).
4. **Extractor for live:** run the **LLM** (timed photometry) with the
   deterministic crosswalk as the safety net. Recommend **not** posting
   `classification` in v1 (regex classification is weak; the flurry showed why).

---

## Numbers cheat-sheet

| | |
|---|---|
| ICARE asks shipped | 12 / 12 (P0–P2) |
| MCP tools / schema version | 9 / v0.3.0 |
| Bot: regex vs LLM postable photometry | 0 → 1 (timed) |
| Flurry | 20 circulars, 22-circular xref graph |
| Classification false positives | 9/12 → 0 after the guard |
| Tests / lint / types | 417 / ruff clean / mypy strict clean |

## Demo script (safe, offline, ~30s each)

```bash
export CIRCEX_TAXONOMY_DIR=references/timedomain-taxonomy/tdtax
# 1. regex — honest "can't time it" path
circex post --from-file docs/fixtures/grb260604c_44877.json --extractor regex
# 2. LLM — timed, postable photometry (needs `ollama serve`)
circex post --from-file docs/fixtures/grb260604c_44877.json --extractor ollama --group-ids 3
```

## Artifacts to screenshot

- The `circex post --extractor ollama` terminal output (Slide 7).
- `docs/flurry_test_grb260604c.md` — the 20-circular output table (Slide 8).
- `docs/design_skyportal_bot.md` — the mapping table (Slide 6).
- `docs/images/eval_example_regex_vs_vidushi.png` — F1 chart (context, if needed).
