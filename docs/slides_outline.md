# Circex — slideshow material

Slide-ready outline, key numbers, diagrams, and a live-demo script. Pull what
you need; every number here is current as of this writing and reproducible.

---

## The one-line pitch

> Circex turns the free text of GCN optical circulars into validated,
> source-grounded JSON — and posts the derived photometry/redshift straight into
> SkyPortal, with every value traceable back to the sentence it came from.

---

## Slide 1 — The problem

- GCN Circulars: the human record of transient follow-up. **40,506** circulars;
  **~18,600** are optical observations.
- They're **free text** — a telescope team types a paragraph and a table.
- Downstream tools (SkyPortal, ICARE) need **structured** data: a redshift, an
  mjd, a magnitude, a filter, a position.
- Hand-extraction across the archive is infeasible. → automate it.

## Slide 2 — What Circex is

- Three **interchangeable extractors** behind one `Extractor` interface:
  - **regex baseline** (transparent, no cost)
  - **Claude** (Haiku / Sonnet, tool-use, schema-enforced)
  - **Ollama** (Mistral-7B, the same model as the published baseline)
- One **output contract**: the `CircularExtraction` Pydantic model → validated
  JSON conforming to `nasa-gcn/gcn-schema`.
- An **MCP server** (9 tools) SkyPortal can query, and a **bot** that posts to
  SkyPortal.

## Slide 3 — Headline result (the regex baseline is serious)

Regex baseline vs the **published** Mistral-7B (Sharma et al. 2026), 500 rows of
the *Swift*-validated gold set:

| Field | Regex F1 | Published Mistral-7B | Δ |
|---|---:|---:|---:|
| Event name | **0.869** | 0.849 | **+0.020** |
| Redshift | **0.858** | 0.690 | **+0.168** |

> A transparent regex baseline already beats the published LLM result. So the
> LLM has a real bar to clear, not a strawman. (Figure: `docs/images/eval_example_regex_vs_vidushi.png`)

## Slide 4 — Every value is auditable (provenance)

- Each extracted field carries a `(start, end, snippet)` pointer into the source
  text.
- The wrong answers become **visibly wrong** — e.g. a bogus classification whose
  provenance snippet is an author's initial `"O"`.
- This is what makes the bot trustworthy: SkyPortal comments cite the exact
  phrase each value came from.

## Slide 5 — Built for SkyPortal/ICARE (12 asks, all shipped)

`extract_text` (live Kafka path) · per-row `obs_mjd`+`obs_time` · canonical
`bandpass` (sncosmo) · `is_detection` · cone search · `taxonomy_path` ·
versioned + CI-gated JSON schemas · telescope alias canonicalization ·
multi-event name lists · redshift-bound handling · streaming idempotency ·
provenance round-trip.

## Slide 6 — The real-world test: the GRB 260604C flurry

A "flurry" = many circulars on one event. **20 circulars, ~14 telescopes**,
fetched + extracted live.

- **Structural spine works:** all 20 resolve to one event; the cross-reference
  graph (**22** circulars) reconstructs itself from a single seed.
- **It found and we fixed real bugs:**
  - classification false positives (`"Overtone"` ← author initial `"O"`): **9 of
    12 garbage → 0** after a short-alias + proper-noun guard.
  - a silent table-parser bug dropping `mag_error` on every table.
  - photometry recall: a common single-detection line was being missed.

(Table: `docs/flurry_test_grb260604c.md` — the full 20-row output.)

## Slide 7 — The bot: Circex → SkyPortal

```
gcn.circulars (Kafka) → extract_text → CircularExtraction
                                            │  skyportal_map.to_actions()
                                            ▼
                         {source, photometry[], redshift, comments}
                                            │
                        dry-run (default)   │   --live + token
                                            ▼
                              POST /sources, /photometry, PATCH redshift, comments
```

- Refuses to post **timeless** photometry (no mjd) — comments it instead of
  fabricating a time.
- Bound redshifts → comment, not a scalar value.
- Unmapped telescopes → flagged, never guessed.

## Slide 8 — Why the LLM matters (the money slide)

Same circular, same bot. **Regex vs LLM:**

| | regex baseline | Ollama / Mistral-7B |
|---|---|---|
| read the table date → `obs_mjd` | ✗ (0 postable) | ✓ `mjd 61199.83` |
| postable photometry | **0** | **1** |

The LLM reads `2026-06-08 20:01:14` and produces a **timed, postable** point.
And the deterministic filter crosswalk **corrects the LLM's calibration error**
(Mistral mislabeled Cousins `Rc` as `sdssr/ab` → bot posts the correct
`bessellr/vega`).

**Live demo (one command):**
```
circex post --from-file docs/fixtures/grb260604c_44877.json --extractor ollama --group-ids 3
```
→
```
POST /sources    {"id": "GRB260604C", "group_ids": [3]}
POST /photometry {"mjd": 61199.83, "filter": "bessellr", "magsys": "vega",
                  "mag": 23.08, "magerr": 0.18, "altdata": {"circex_circular_id": 44877}}
```

## Slide 9 — Engineering quality

- **417 tests** passing; `ruff` + `mypy --strict` clean; CI on Ubuntu + Windows.
- CI also typechecks the **TypeScript MCP bridge** and gates **schema drift +
  version bumps** (downstream consumers pin to a schema version).
- Schema at **v0.3.0**, semver-published for ICARE.

## Slide 10 — Status & what's next

- **Done:** all three extractors, the eval harness, the 9-tool MCP server +
  bridge, the SkyPortal bot (dry-run), the `circex post` CLI.
- **Next:** point the bot at a SkyPortal sandbox (token + instance), a GCN Kafka
  consumer for live triggering, and the full 500-row four-way eval (queued for a
  faster box).
- **Recommendation for live:** run the **LLM extractor** (timed photometry) with
  the deterministic crosswalk as the safety net.

---

## Demo script (safe, offline, ~30s each)

```bash
# 0. setup (once)
export CIRCEX_TAXONOMY_DIR=references/timedomain-taxonomy/tdtax

# 1. regex on the flurry seed — honest "can't time it" path
circex post --from-file docs/fixtures/grb260604c_44877.json --extractor regex

# 2. the same circular via the LLM — timed, postable photometry (needs `ollama serve`)
circex post --from-file docs/fixtures/grb260604c_44877.json --extractor ollama --group-ids 3

# 3. a clean circular — full happy path (source + photometry + redshift + comment)
#    (any circular JSON with a dated table + RA/Dec + z works)
```

## Numbers cheat-sheet

| | |
|---|---|
| Circulars in archive / optical | 40,506 / ~18,600 |
| Regex vs published Mistral-7B | +0.020 (event), +0.168 (redshift) F1 |
| GRB 260604C flurry | 20 circulars, 22-circular xref graph |
| Classification false positives | 9/12 → 0 after the guard |
| Bot: regex vs LLM postable photometry | 0 → 1 (timed) |
| Tests / lint / types | 417 / ruff clean / mypy strict clean |
| MCP tools / schema version | 9 / v0.3.0 |

## Figures / artifacts to screenshot

- `docs/images/eval_example_regex_vs_vidushi.png` — the F1 comparison chart.
- `docs/flurry_test_grb260604c.md` — the 20-circular flurry output table.
- The `circex post --extractor ollama` terminal output (Slide 8).
- `docs/design_skyportal_bot.md` — the mapping table.
