# Fine-tuning readiness — eval + dataset

Prerequisites worked through before committing GPU time to a Mistral-7B fine-tune.
Terminology: **Mistral-7B here is the generative _extractor_** (`OllamaExtractor`),
not a classifier. The topic _classifier_ is S25's MiniLM (already fine-tuned
upstream; we only consume its labels).

## 1. Eval — where does regex actually stand?

`circex eval --extractors regex --gold vidushi` over 644 circulars with gold
support (520 redshift, 544 event). Report: `reports/eval_regex_vidushi.md`.

| Field | regex F1 | published Mistral-7B F1 | Δ |
|---|---|---|---|
| **redshift** | **0.865** (P 0.873 / R 0.858) | 0.710 (P 0.918 / R 0.579) | **+0.155** |
| **event name** | **0.884** (P 0.819 / R 0.960) | 0.867 | +0.017 |
| telescope | — (not extracted) | 0.108 | — |

At real scale, **regex beats the published Mistral-7B baseline on both
gold-backed fields.** Mistral's redshift *precision* is higher (0.918) but its
recall collapses (0.579) — it misses many redshifts regex catches.

## 2. The data gap (the real blocker)

The only gold with populated values is **redshift + event name** (Vidushi/Swift,
via `swift_gold`). The 50 hand-labels (`data/labels/hand_v1`) are early-1990s GRB
circulars that are labeled **all-null** — no photometry, position, or
classification — so `circex eval --gold data/labels/hand_v1` reports zero gold
support across every field (`reports/eval_regex_handlabels.md`). That is not a
harness bug; those circulars simply contain nothing to extract.

Consequence: **for photometry, localization, and classification — the fields
where an LLM would most plausibly beat regex — there is no gold to measure with
and no labels to train on.** A fine-tune there is currently unmeasurable and
untrainable.

## 3. Dataset producer (`circex dataset`)

Turns labeled circulars into Mistral instruction-tuning chat JSONL (train/val):

```bash
circex dataset --source vidushi --out data/finetune          # 489 train + 55 val
circex dataset --source data/labels/hand_v1 --out data/ft_labels
```

Each line: a user turn (extraction instruction + circular body) and an assistant
turn (target JSON). The Vidushi source yields **544 validated examples** today
(event + redshift + telescope). The full-field set comes from the
`circex annotate` → human-validation (`tylerbarna/gcn-nlp-label`) →
`circex dataset --source <labels>` pipeline — the labels for photometry/
classification have to be produced there first.

## 3b. Full-field gold — the annotate labeling pass (`data/labels/flurry_v1`)

The Vidushi gap (no photometry/localization/classification gold) is now partly
filled. The GRB 260604C flurry — 13 circulars we cross-checked against SkyPortal
— was labeled into validated `.label.json` gold (27 photometry rows), *including
the detections regex cannot map* (MASTER unfiltered, LAST clear-band, GOTO-L) and
the SVOM position regex misses. Bodies are co-located under `sources/` so the set
is self-contained; run `circex eval --gold data/labels/flurry_v1
--circulars-dir data/labels/flurry_v1/sources`.

First full-field regex numbers (`reports/eval_regex_flurry.md`):

| Field | regex F1 | P / R | gold rows | what it reveals |
|---|---|---|---|---|
| event | 1.000 | 1.0 / 1.0 | 13 | solved |
| localization | 0.800 | 1.0 / 0.667 | 3 | misses one "R.A., Dec. …, … degrees" format |
| **photometry** | 0.826 | **1.0 / 0.704** | 27 | **perfect precision, 70% recall** — misses the 8 unmappable-filter (clear/unfiltered/GOTO-L) detections |
| classification / redshift | — | — | 0 | none in this event (GRB afterglow) |

The signal for a fine-tune: regex **never fabricates** photometry (precision 1.0)
but leaves ~30% recall on the table — exactly the odd filters/formats an LLM
generalizes to. Classification/redshift still need SN / spectroscopy circulars to
get gold. The full-field labels also seed the first extraction training examples:
`circex dataset --source data/labels/flurry_v1`.

## 3c. Classification + spectroscopic-redshift gold (`data/labels/spec_v1`)

The flurry (GRB afterglow) had no classification/redshift gold. Searching the
40,506-circular 2025 archive surfaced SN-classification and spectroscopic-redshift
circulars; 10 diverse ones were labeled — SN Ia/Ic, spectroscopic absorption GRB
redshifts (z=2.163, 0.767), host (0.714) and photometric (0.199) redshifts, two
redshift bounds (z≥0.09, z≥0.42), and two deliberate traps: GRB "type I/II"
(short/long population, **not** an SN type → classification null) and a nearby
galaxy's z (GOTO25cqo's SN is z=0.18; the 0.169 galaxy is explicitly excluded).

First numbers for the weak fields (`reports/eval_regex_spec.md`):

| Field | regex F1 | P / R | gold | verdict |
|---|---|---|---|---|
| **classification** | **0.143** | **0.10 / 0.25** | 4 | fires on nearly every circular; misses 3/4 real SN types |
| redshift value | 0.875 | 0.78 / 1.0 | 7 | perfect recall, over-extracts on bounds/traps |
| redshift type | 0.000 | 0 / 0 | 4 | host/emission/absorption not classified |
| event | 0.500 | 0.5 / 0.5 | 10 | SN designations harder than GRB names |

**Classification F1 = 0.143 is the hard number that justifies the SN-type
classifier** — regex's precision is 0.10 here (rampant false positives despite the
guards). Redshift *value* is strong on recall but loses precision to bounds/traps;
redshift *type* is unhandled. These labels seed the first classification/redshift
training examples (`circex dataset --source data/labels/spec_v1`).

## 4. Recommendation

A Mistral-7B **extractor** fine-tune is weakly justified *right now*:

- On the only gold-backed fields (redshift, event) **regex already beats the
  baseline**, so the upside of a fine-tune there is small and possibly negative.
- On the fields where an LLM could help (photometry, classification) there is
  **no labeled data**, so a fine-tune can be neither trained nor evaluated.

Ordered path to a *justified* fine-tune:

1. **Build full-field labels** — run `circex annotate` over a modern optical
   subset, validate via the gcn-nlp-label UI, land them as `.label.json`.
2. **Re-run the eval** on those labels to find the fields where regex actually
   loses (candidate: irregular table layouts, in-prose classification).
3. **Fine-tune targeting those fields** (dataset is ready to build), or — cheaper
   and more surgical — a small **SN-type classifier** (DistilBERT/MiniLM head)
   for the `classification` field, our weakest component (9/12 false positives
   before the guards). That runs on the Mac and needs far less data than a 7B.

## Status of the list

| Item | State |
|---|---|
| Regex vs baseline | ✅ confirmed at scale: redshift +0.155, event +0.017 |
| Eval has run | ✅ `reports/eval_regex_vidushi.md` (+ hand-label gap documented) |
| Training-data pipeline | ✅ `circex dataset`; 544 validated examples generated |
| Full-field labels | ⏳ needs the annotate → human-validation pass |
| Compute (GPU fine-tune) | ⏸ deferred (out of scope) |

## 5. SN-type classifier — built (`circex classify-train`)

The classification field (regex F1 0.143) was the clear fine-tune target, so it's
now built — as a **dependency-free multinomial Naive Bayes** classifier, not a
transformer: the signal is lexical, the data is small, and a closed-form CPU fit
runs in CI and on the Mac (a transformer stays a drop-in on the same interface).

- **Training data** is harvested from the 40,506-circular archive
  (`circex/classify/harvest.py`): 187 single-type positives (Ia/II/Ic/TDE/…) plus
  a deterministic NONE sample of real GRB/afterglow/detection circulars, with the
  GRB "type I/II" (short/long population) trap excluded. The `spec_v1` gold is
  held out of training.
- **The decisive feature is the NONE class** — regex fires a classification on
  nearly every circular (precision 0.10); trained on real negatives, NB abstains.

On the held-out `spec_v1` gold:

| classifier | F1 | P / R |
|---|---|---|
| regex | 0.143 | 0.10 / 0.25 |
| **Naive Bayes** | **0.615** | 0.44 / **1.00** |

**4.3× the F1, and recall 1.0** (catches every SN type) — with real precision
headroom (0.44: it still over-fires on some negatives). The model
(`data/models/sn_type.json`, gitignored — derived from the gitignored archive) is
built with `circex classify-train`. Next increments: wire it in as the
`classification` source behind a model-path flag; grow the gold to tighten
precision; a transformer if the ceiling demands it.
