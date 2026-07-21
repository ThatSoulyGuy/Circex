# Reviewer-response data pack (mhp260719 comments)

All numbers regenerated 2026-07-20 from the released Sha26 table, the cached
constrained-Mistral run (v0.2 weights, prompt 2026-06-04), and a fresh local
regex run — using the whitespace-fixed event-name comparator now in the repo.
Everything here is paste-ready; tables are plain text for Pages/Word conversion.

---

## 1. Corrected Table 1 — now four fields, re-scored comparator

    Field              Support   Regex                 Mistral-7B (constr.)   Mistral-7B (Sha26)
    Event name           400     P .787 R .970 F .869  P .738 R .917 F .818   P .764 R .955 F .849
    Redshift             383     P .870 R .854 F .862  P .932 R .937 F .935   P .903 R .559 F .690
    Redshift measure     362     P .600 R .041 F .078  P .881 R .978 F .927   P .801 R .989 F .885
    Telescope name       400     n/a (not attempted)   P .127 R .075 F .094   P .088 R .110 F .098

Changes vs. the current draft, each of which the text must absorb:

- **Constrained-Mistral event name is 0.818, not 0.767.** The old comparator
  scored `GRB971214` (as old Circulars write it) vs. gold `GRB 971214` as a
  mismatch; 23 of the 56 published mismatches were this whitespace artifact.
  Regex (0.869) and Sha26 (0.849) are unchanged — their outputs use the spaced
  form.
- **Redshift measure is a NEW fourth row** (answers "I don't believe only three
  fields"). Sha26's released table contains four Actual/Predicted field pairs:
  Redshift, GRB Number, Telescope Name, and Redshift Type — where "Redshift
  Type" takes the values Spectroscopic/Photometric (our schema's
  `redshift_measure`). Our adapter had expected emission/absorption/host and
  mapped every value to null, which is why the draft wrongly said the column
  was empty. Scored properly: constrained Mistral 0.927, Sha26 0.885, regex
  0.078 (its measure heuristic rarely fires; it needs explicit context words).
- **Gold-set size correction:** the released `redshift_accuracy.csv` has
  **644 records**, not 13,593 — 13,593 is the physical line count (the `Text`
  column holds multi-line quoted Circular bodies). Our 500-row slice is 78% of
  the table. Every "13,593-row" in the draft must change.
- Nulls in the table are sentinel strings ("No Information", "No Redshift").
  Non-sentinel support in our slice: redshift 400 (383 parseable to a float),
  GRB number 400, telescope 400, redshift measure 362.

## 2. Table 2 — unchanged, re-verified

    Extractor               Precision   Recall   F1
    Regex                     0.870     0.854   0.862
    Mistral-7B (constr.)      0.932     0.937   0.935
    Mistral-7B (Sha26)        0.903     0.559   0.690

## 3. Failure-mode breakdown of Sha26's redshift misses (the abstract's claim)

Of 383 gold redshifts in the slice, Sha26's released predictions recover 214.
The 169 misses decompose as:

    Non-emitted (predicted "No Redshift" where the gold has one)   160   (95%)
    Incorrectly extracted value (both set, values differ)            9    (5%)

(Plus 14 false positives where the gold has no redshift.) Suggested sentence:
"Of Sha26's 169 redshift misses on this slice, 160 (95%) are Circulars where
the pipeline returned no redshift at all, and only 9 (5%) are incorrectly
extracted values — the published deficit is a failure to answer, not a failure
of extraction accuracy."

Wording caution: the released table records the output "No Redshift", which
does not distinguish unparseable model output discarded upstream from a
genuine no-redshift answer. Let the controlled experiment (same weights,
constrained decoding, recall 0.559 -> 0.937) carry the mechanism; the split
above carries the counts.

## 4. Event names: why constrained Mistral trails Sha26 (0.818 vs 0.849)

Residual error taxonomy after the comparator fix (33 mismatches):

- **30 of 33 are suffix-letter truncation** (`GRB 050525` vs gold
  `GRB 050525A`). Of these 30:
  - **13**: the lettered designation appears nowhere in that Circular's text —
    the gold is the retrospective Swift catalog name. Unextractable by any
    single-Circular system that reports only what the text states; a
    task-definition ceiling, not a model error.
  - **17**: the letter is present in the text and the model dropped it — a
    genuine model error.
- Ruled out: the grammar's string caps (`maxLength` 128 vs ~11-char
  designations) cannot truncate designations.
- False positives are nearly identical (97 vs Sha26's 100), nearly all on
  gold-"No Information" rows (pre-Swift-era Circulars): both systems extract
  the GRB the text names; the gold simply has no catalog match. Penalizes both
  equally.

## 5. v0.2 purity check (no server run needed)

24 of the 500 cached constrained-Mistral rows were later overwritten by
v0.3-model outputs (cache-key collision before the prompt-version bump).
Excluding them changes nothing at reported precision:

    Field            all 500   pure-v0.2 476   |delta|
    Event name        0.818       0.816         0.003
    Redshift          0.935       0.933         0.002
    Telescope         0.094       0.087         0.008

Report the 500-row numbers; a footnote can cite this robustness check.

## 6. Worked example for the new Figure 1 (Circular -> JSON)

There is **no intermediate step to show**: the `CircularExtraction` object IS
the gcn-schema-conforming JSON (its JSON Schema is exported from the Pydantic
model). Two-panel figure: Circular text left, JSON right.

Recommended example — GCN 44877 (GRB 260604C, SAO RAS follow-up): a real
fixed-width photometry table parsed into a structured row, with the provenance
span pointing at the exact table line.

Text panel (truncate to):

    A. Moskvitin (SAO RAS), O. Spiridonova (SAO RAS), A. Pozanenko (IKI), ...
    We observed the field of long GRB 260604C discovered by Fermi
    (The Fermi GBM team, GCN 44822; ...) with the Zeiss-1000 1-m telescope
    of SAO RAS ... 12 x 300 sec. images in Rc band on June 08,
    20:01:14--21:07:58 UT.

    Date       UTstart  t-T0    Exp.    Filter Mag +/- Err.   UL(3sigma)
    2026.06.08 20:01:14 4.01102 12*300  Rc     23.08 +/- 0.18  23.8

JSON panel (truncate to):

    {
      "circular_id": 44877,
      "event": { "event_name": "GRB 260604C" },
      "follow_up": { "reference": { "gcn_circulars": "44822,44831,..." } },
      "photometry": [{
        "filter": "R", "bandpass": "bessellr",
        "mag": 23.08, "mag_error": 0.18, "mag_system": "Vega",
        "obs_time": "2026-06-08T20:01:14Z", "obs_mjd": 61199.83419,
        "is_detection": true
      }],
      "classification": { "classification": "GRB", ... },
      "provenance": {
        "photometry[0]": {
          "start": 1073, "end": 1135,
          "snippet": "2026.06.08 20:01:14 4.01102 12*300 Rc  23.08 +/- 0.18  23.8"
        }, ...
      }
    }

Optional companion (discovery side): GCN 44827 (MASTER OT) shows event +
sexagesimal coordinates converted to decimal degrees
(`(RA, Dec) = 14h 57m 49.59s +28d 49m 03.0s` -> `ra: 224.4566, dec: 28.8175`)
with its own provenance span. Caption idea: "A GCN Circular and the validated
CircularExtraction JSON Circex produces from it. Every populated field carries
a provenance span pointing back into the source text."

## 7. Replacement figure

**File: `docs/images/eval_4way_v2.png`** (200 dpi). Top panel: per-field F1
for the four fields of §1 above (regex telescope shown as hatched n/a — it
does not attempt the field). Bottom panel (replaces ΔF1): per-model extraction
latency on a log axis — filled dot p50, open dot p95 — with marginal cost
annotated; the Sha26 row is marked "not reported" (the release contains no
latency or cost data). Colors are the Wong (2011) colorblind-safe palette,
identical to the current figure.

Draft caption: "Figure 1. Top: per-field F1 for the regex baseline, the
grammar-constrained Mistral-7B extractor, and the published Sha26 Mistral-7B
predictions, on 500 rows of the Sha26 Swift-validated gold set. Hatching
denotes a field the extractor does not attempt. Bottom: per-Circular
extraction latency (log scale; filled = median, open = 95th percentile) and
marginal cost. Both local extractors run at zero marginal cost; the Sha26
release does not report latency."

## 8. Low Table 3 scores — error analysis (for §4.3)

- **Classification (support = 7 — lead with that; the estimate is
  indicative).** Constrained Mistral: 1 TP / 11 FP / 6 FN. The misses are
  gold-`Supernova` Circulars where the model returned null (its instruction is
  to abstain unless confident); the false positives are `GRB` emitted as a
  classification — an event type, not a spectroscopic class. Regex: 1 TP /
  105 FP (precision 0.009): keyword triggers fire "GRB"/"afterglow" on
  essentially every GRB Circular, plus star-name contaminants.
- **Redshift type (emission/absorption/host; support = 32).** Constrained
  Mistral: 16 TP / 36 FP / 16 FN — dominated by inference false positives:
  emitting `host` or `absorption` when the Circular names no spectral feature,
  plus genuine confusions (gold absorption -> predicted host). Regex errs the
  opposite way (11 TP / 8 FP / 21 FN): conservative, misses stated types.

## 9. Telescope name (for §2.2 and §3.2.2)

- §2.2 sentence: the regex baseline contains no telescope sub-parser by
  design — telescope names are proper nouns with no lexical regularity (a
  gazetteer/alias problem, not a pattern problem) — hence n/a.
- §3.2.2: both Mistral configurations transcribe the name as written in prose
  while the gold uses Swift catalog short codes; under exact-string comparison
  both score ~0.09 identically. Real pairs from the data: gold `VLT` (129
  rows) vs predicted `ESO VLT` / `ESO VLT UT3 (Melipal)`; gold `NOT` vs
  `Nordic Optical Telescope (NOT)`; gold `GTC` vs `GTC (10.4m)`. Extraction
  succeeds; canonicalization is simply unattempted — the alias map that fixes
  this is deterministic post-processing, not model capability.

## 10. The 97.2% (verified against the arXiv abstract)

Exact sentence: "our simple system, with the help of prompt-tuning, output
parsing, and retrieval augmented generation (RAG), can achieve an accuracy of
97.2% for redshift-containing Circulars." Metric: **accuracy**, conditional on
redshift-containing Circulars (post-retrieval denominator). The related 96.8%
is the RAG pipeline's retrieval accuracy. Cite as "accuracy of 97.2% on
redshift-containing Circulars".

## 11. Glossary definitions (rework into your own voice)

- **llama.cpp** — an open-source C/C++ inference engine that serves quantized
  open-weight language models on local hardware, exposing an OpenAI-compatible
  HTTP API; it implements the grammar-constrained decoding used in §3.
- **Naive Bayes classifier** — a probabilistic text classifier that applies
  Bayes' theorem under the assumption that word occurrences are independent
  given the class; used here as a lightweight supernova-type classifier
  trained on Circular text.
- **Pydantic v2** — a Python data-validation library in which schemas are
  declared as typed model classes; validation is automatic on construction,
  and each model exports a JSON Schema (the mechanism behind our
  gcn-schema-conforming output).
- Suggested additions: **grammar-constrained decoding / GBNF** (the sampler
  may only emit tokens that keep the output inside a formal grammar compiled
  from the JSON Schema), **JSON Schema**, **RAG**, **Kafka** (the message bus
  carrying the live `gcn.circulars` stream), **SkyPortal**, **provenance
  span** (character-offset pointer from an extracted value back into the
  source text), **quantization** (the Q4_K_M compression that lets a 7B model
  serve on one GPU). Delete the trailing "..." row. Skip F1/precision/recall —
  the audience knows them.
