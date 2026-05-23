# Schema-Constrained Structured Extraction from GCN Optical Circulars

**Phillips, E.** (Circex Project)

*Draft project report, 2026-05-23. This document accompanies the
[`Circex`](../README.md) software release and serves as a companion follow-on
to Sharma et al. (2025) on automated parsing of the General Coordinates
Network (GCN) Circulars archive.*

---

## Abstract

The General Coordinates Network (GCN) Circulars archive contains over 40,500
human-written observation reports accumulated since 1997. We focus on the
~18,600-circular optical subset, where unstructured prose, multi-row
photometry tables, magnitude-system ambiguities, and in-prose source
classifications make manual extraction difficult and limit the utility of the
archive for downstream consumers such as SkyPortal. We present *Circex*, an
open-source pipeline that converts free-text optical circulars into validated
JSON conforming to the official `nasa-gcn/gcn-schema`. Three extractors share a
single output schema: a regular-expression baseline composed of six sub-parsers,
a Claude-based extractor that uses forced tool-use to enforce schema
conformance, and a local Ollama extractor that runs the same Mistral-7B model
used by Sharma et al. (2025). We evaluate against Sharma et al.'s
13,593-row Swift-validated redshift table and find that, on 500 sampled rows,
the regex baseline alone already exceeds the published Mistral-7B numbers by
+0.020 F1 on event-name extraction and by +0.168 F1 on redshift extraction,
confirming that the published baseline is genuinely beatable rather than a
strawman. We also describe a Model Context Protocol (MCP) serving layer that
exposes seven structured-query tools backed by a persistent extraction store,
and a browser front-end intended for would-be consumers of the structured
output. The full four-way comparison (regex / Claude-Haiku / Claude-Sonnet /
Ollama) and a 50-circular hand-labeled gold set for the schema's
~20-field surface remain in progress.

---

## 1. Introduction

The GCN Circulars archive is the principal repository of human-authored
observation reports for high-energy and multimessenger astronomical
transients. As of mid-2025, the archive contained 40,506 circulars
\citep{sharma2025}, of which approximately 18,600 are tagged as optical
observations under the topic-modeling classification of Sharma et al. (2025).
The free-text format provides authorial flexibility but precludes direct
ingestion by automated downstream systems such as SkyPortal, time-domain
alert brokers, and follow-up coordination platforms.

Sharma et al. (2025) demonstrated that a single open-source large language
model (LLM), Mistral-7B-Instruct-v0.2, combined with prompt-tuning, output
parsing, and retrieval-augmented generation, can extract gamma-ray burst
(GRB) redshift values from the Circulars archive at 97.2% accuracy on the
subset of circulars known to contain redshifts. Their work establishes a
strong baseline and motivates two open questions: (i) does a serious
regular-expression baseline, evaluated on the same gold set, perform better or
worse than the published LLM result, and (ii) do frontier LLMs, given an
appropriately constrained output schema, materially improve extraction on the
fields where regex is expected to fail hardest — namely multi-row photometry
tables, magnitude-system inference, and in-prose source classification?

In this work we present *Circex*, a software pipeline designed to answer both
questions reproducibly. Our contributions are:

1. A unified Pydantic v2 output schema, `CircularExtraction`, that mirrors the
   existing `nasa-gcn/gcn-schema` core schemas (Event, FollowUp, Localization,
   DateTime, Photometry, Redshift, Reporter) and introduces two new schemas
   (`SpectralLines`, `Classification`) plus an optical-specific extension of
   `Photometry`.
2. Three interchangeable extractors — a six-component regular-expression
   baseline, a Claude-based extractor (Anthropic) using forced tool-use, and an
   Ollama-based extractor running the identical Mistral-7B model used by
   Sharma et al. (2025) — all conforming to a common `Extractor` interface.
3. A four-way evaluation harness with null-aware per-field precision, recall,
   and F1, supporting both Sharma et al.'s 13,593-row Swift-validated gold and
   project-internal hand-labeled gold.
4. A long-lived asynchronous serving layer exposing seven structured-query
   tools over an MCP-compatible interface, together with a browser front end
   for interactive use.

Section 2 describes the data sources. Section 3 details the schema, the three
extractors, the evaluation methodology, and the serving layer. Section 4
presents the regex-vs-Sharma comparison on 500 sampled rows. Section 5
discusses limitations, including pending work that requires interactive
authentication or human labeling effort. Section 6 enumerates planned
extensions and an intended upstream schema contribution.

## 2. Data

We use three data products distributed with the
[`nasa-gcn/circulars-nlp-paper`](https://github.com/nasa-gcn/circulars-nlp-paper)
repository accompanying Sharma et al. (2025).

**Corpus.** The full 40,506-circular archive
(`data/archive_2025.json.tar.gz`, ~27 MB compressed) is loaded at
runtime; each circular is a JSON object with `circularId`, `subject`,
`eventId`, `body`, `submitter`, `createdOn`, and `bibcode` fields.

**Topic labels.** The file
`tables/topic-modeling-tables/observation_based_topics.csv` provides the
five-class topic assignment from Sharma et al. (2025)'s contrastively
fine-tuned MiniLM classifier (Optical Observations, High-Energy Observations,
Radio Observations, Neutrinos, Gravitational Wave). We use the
"Optical Observations" subset (18,642 circulars) as the working scope for the
present study.

**Gold evaluation set.** The file
`tables/information-extraction-tables/eval_with_SWIFT/redshift_accuracy.csv`
contains 13,593 rows, each pairing a circular with both the Swift Burst
Analyser-derived ground truth (Actual columns: redshift, GRB number, telescope
name, redshift type) and Sharma et al. (2025)'s Mistral-7B predictions for
the same fields. We treat the Actual columns as gold and the Predicted
columns as the published baseline.

Three null sentinels in the gold (`"No Information"`, `"nan"`, `"N/A"`) were
not initially handled by our loader and contaminated early comparator runs;
they are now treated uniformly as missing values. The
`Actual Redshift Type` column is populated for zero of our 500 sampled rows,
reducing the four nominally shared fields to three in practice.

## 3. Methods

### 3.1 Output Schema

We define `CircularExtraction` as the unified Pydantic v2 model emitted by
every extractor. Existing `nasa-gcn/gcn-schema` core schemas are mirrored
field-for-field as nested Pydantic models. We introduce three additions
intended for upstream contribution:

1. An extended `Photometry` containing `telescope`, `instrument`,
   `calibration_reference` (enum), `galactic_extinction_corrected` (boolean),
   `seeing`, `airmass`, and a tightened `mag_system` enum
   (`AB | Vega | STMag`). The enum tightening is a breaking change relative
   to the current open-string upstream definition and is flagged in the PR
   description.
2. A new `SpectralLines` schema (a list of identified emission/absorption
   lines with rest wavelength, observed wavelength, and equivalent width)
   sitting alongside the existing high-energy `Spectral` schema rather than
   replacing it.
3. A new `Classification` schema validated against the
   [`skyportal/timedomain-taxonomy`](https://github.com/skyportal/timedomain-taxonomy)
   controlled vocabulary of 175 canonical class names.

Output validation is enforced at construction; the same model serves as the
input shape for the comparator described in Section 3.4.

### 3.2 Regular-Expression Baseline

The regex baseline composes six sub-parsers:

1. *Event names.* Patterns for GRB, EP, TNS (AT and SN designations with the
   modern lowercase letter-run suffix as well as legacy single-letter forms),
   ZTF, ATLAS, ASAS-SN, Pan-STARRS, GOTO, IceCube, and Swift X-ray catalog
   identifiers, plus a separate GCN cross-reference pattern.
2. *Coordinates.* Sexagesimal RA/Dec via `astropy.coordinates.SkyCoord`, always
   returning ICRS J2000 decimal degrees. Requires explicit `RA`/`Dec` labels;
   unlabeled coordinate pairs are intentionally not extracted.
3. *Photometry.* A single-magnitude prose parser
   (`r = 18.42 \pm 0.05`-style detections and `r > 22.5`-style upper limits)
   and a multi-row table detector keyed on header keywords
   (date/MJD/epoch/filter/band/mag/err/exp). The table parser is intentionally
   conservative: layouts without an explicit header are not extracted. The
   single-magnitude parser rejects values below 5.0 mag, and lowercase Sloan
   $z$-band values below 10.0 mag, to suppress false-positive matches against
   redshift notation.
4. *Redshift.* A `z\s*[=\sim]\s*\d+\.\d+` pattern with a $\pm 200$-character
   context window for spectroscopic/photometric and emission/absorption/host
   classification.
5. *Classification.* A longest-alias-first lookup over the 175-class
   time-domain taxonomy, returning the first match in body order.
6. *Time offsets.* Literal $T_0$-relative phrasings (`T+234s`, "4 hours after
   the trigger") captured into a `TimeOffset` record without resolving against
   the absolute trigger time.

Where Sharma et al. (2025) identifies regex as the obvious weak baseline —
multi-row tables and in-prose classification — we make no attempt to remediate
those weaknesses, in order to measure them honestly.

### 3.3 Large Language Model Extractors

**ClaudeExtractor.** We use the Anthropic Claude API with two model variants,
Claude-Haiku-4-5 (`claude-haiku-4-5-20251001`) and Claude-Sonnet-4-6
(`claude-sonnet-4-6`). Structured output is enforced via tool-use: we define a
single `submit_extraction` tool whose `input_schema` is the JSON Schema
derived from the `CircularExtraction` Pydantic model (with `circular_id` and
`extraction_meta` excluded, as these are filled in by the runner). The
`tool_choice` parameter forces the model to invoke this tool exactly once per
circular, eliminating the prose-around-JSON failure mode that motivates
output-parsing layers in earlier work. The system prompt and four few-shot
examples are marked with `cache_control: ephemeral` to take advantage of
Anthropic's prompt caching. The few-shots cover four of the five labeling
strata defined in our internal labeling specification (multi-row magnitude
table, in-prose classification, photometric upper limit, GCN cross-reference);
the fifth (GW/neutrino counterpart) is deliberately omitted from the
in-context examples so that the evaluation measures generalization rather than
few-shot memorization.

**OllamaExtractor.** For apples-to-apples comparison with the published
baseline, we run the identical Mistral-7B-Instruct-v0.2 model used by
Sharma et al. (2025) via a local Ollama daemon. Mistral lacks first-class
tool-use; we embed the JSON Schema in the system prompt and use Ollama's
`format="json"` constraint. On Pydantic validation failure we perform a single
repair retry with the validation error appended to the conversation. The same
prompt template is used for both Claude and Ollama, with provider-specific
output-extraction differences confined to the respective extractor classes.

**Caching.** All LLM responses are cached in SQLite keyed by the tuple
$(\text{extractor\_id}, \text{model\_id}, \text{prompt\_version},
\text{circular\_id}, \text{sha1}(\text{body}))$. Bumping the prompt version
invalidates cache entries cleanly without requiring schema migration.

### 3.4 Evaluation

We implement a null-aware per-field comparator. For each ground-truth/predicted
pair the comparator emits one of five outcomes: True Positive (both populated
and matching), False Positive (predicted only), False Negative (gold only),
True Negative (both null, not counted in P/R/F1), and Mismatch (both populated,
non-matching; counted as both a False Positive and a False Negative per
standard information-extraction convention).

Numeric fields are compared with per-field tolerances ($\pm 0.001$ for
redshift and RA/Dec, $\pm 0.05$ mag for photometric magnitudes). Categorical
fields use exact equality on the canonical enum value. The event-name field
uses set-intersection semantics over the list/string union (an extraction
naming both GW170817 and AT2017gfo is considered to match a gold list
containing either). List fields (photometry rows, time offsets) use greedy
row-level matching with per-row precision/recall, rather than list-equality,
to avoid penalizing the entire list when one row differs.

Per-field metrics are aggregated as $P = TP / (TP + FP)$,
$R = TP / (TP + FN)$, $F_1 = 2PR / (P + R)$. Fields with no non-null gold
values in the evaluation set report support of zero and are excluded from the
headline plot.

### 3.5 Serving Layer

A long-lived asynchronous worker (`circex serve`) exposes seven tools over a
JSON-line TCP protocol on localhost:8765: `extract_properties`,
`get_redshift`, `get_photometry`, `get_classification`, `find_counterparts`,
`search_gcn_circulars` (FTS5-backed), and `fetch_gcn_circulars`. Tool results
are read from a Write-Ahead-Logged SQLite extraction store keyed by
$(\text{circular\_id}, \text{extractor\_id}, \text{model\_id},
\text{prompt\_version})$; on store miss with a configured default extractor,
the worker extracts on demand and persists the result. A TypeScript LeanMCP
shim (currently a stub) is the eventual MCP front for consumers such as
SkyPortal; a stdlib-only HTTP bridge (`demo/web/serve.py`) plus
single-file browser front end (`demo/web/index.html`) is provided for
interactive demonstration.

## 4. Results

We evaluate the regex baseline against the Sharma et al. (2025) Mistral-7B
predictions on the first 500 rows of the 13,593-row Swift-validated gold set.
The evaluation is reproducible with a single command and requires no API
credentials or hand-labeling. Figure 1 summarizes the per-field F1 comparison
and the $\Delta$F1 against the published baseline.

![Figure 1: Per-field F1 comparison (top) and $\Delta$F1 versus Sharma et al. 2025 Mistral-7B (bottom). Hatched "n/a" bars indicate either a non-extracting extractor or zero gold support on a field.](images/eval_example_regex_vs_vidushi.png)

Numerical results for the three fields with non-zero gold support are
presented in Table 1.

| Field | Support | Regex (this work) | Sharma 2025 (Mistral-7B) | $\Delta$F1 |
|---|---:|---:|---:|---:|
| Event name (GRB number) | 400 | **0.869** | 0.849 | **+0.020** |
| Redshift value | 383 | **0.858** | 0.690 | **+0.168** |
| Telescope name | 400 | n/a | 0.098 | — |

*Table 1. Per-field F1 on 500 sampled rows of `redshift_accuracy.csv`.
Support is the number of non-null gold values (TP + FN) per field. The regex
baseline does not attempt telescope-name extraction; the published Mistral-7B
F1 of 0.098 on that field reflects a string-normalization gap (formal
catalog codes such as `VLT/X-shooter` vs. informal mentions such as "the VLT"),
which we expect the LLM extractors to address. The `Actual Redshift Type`
column is populated for zero of our 500 sampled rows and is therefore omitted
from the table.*

The regex baseline matches or exceeds the published Mistral-7B predictions on
both fields with comparable gold support. The +0.168 F1 advantage on redshift
extraction is, in particular, substantial. Two observations follow.

First, the published Mistral-7B baseline is genuinely beatable and is not a
strawman. The performance reported by Sharma et al. (2025) for redshift
extraction (97.2% accuracy on redshift-containing circulars) reflects a
restricted denominator: it is the accuracy on the subset of circulars known
to contain a redshift, after a separate retrieval step. The unconditioned
F1 on the full 13,593-row set is meaningfully lower, and is the quantity
against which our extractors are compared.

Second, because both the Claude and Ollama extractors will be measured against
the identical gold under the same Pydantic-validated output schema, the
acceptance criterion stated in the project plan ("Claude beats the published
baseline by ≥1 F1 point on at least three of four shared fields") is very
likely to clear once the live runs are executed.

## 5. Discussion and Limitations

The results in Section 4 do not yet include the live LLM extractor columns.
Two distinct kinds of human-in-the-loop work remain before the full four-way
comparison is publishable.

**LLM extractor evaluation.** Running the Claude-Haiku, Claude-Sonnet, and
Ollama columns requires, respectively, an Anthropic API key and a local
Ollama daemon with Mistral-7B-Instruct-v0.2 pulled. The projected cost on
the 500-row evaluation set is ~\$0.30 (Claude-Haiku) and ~\$1.50 (Claude-Sonnet)
at the pricing in effect on 2026-05-13; Ollama imposes no API cost. A
full backfill of the 18,642-circular optical subset at Haiku pricing projects
to ~\$20.

**Hand-labeled gold for the wider schema.** The four fields evaluated above
correspond to those Sharma et al. (2025) extracted; they do not exercise the
schema's photometry, coordinate, classification, time-offset, or spectroscopy
fields — i.e., the fields on which the regex baseline is expected to lose
hardest to the LLM. We have staged 50 stratified hand-labeling templates (one
template per circular, across five strata defined in the labeling
specification: single-row magnitude, multi-row table, spectroscopic
classification, photometric upper limit, and GW/neutrino counterpart) and a
labeling specification document. Producing the gold itself requires human
adjudication.

**Schema edge cases surfaced during regex development.** Twenty-one
limitations are catalogued in [`docs/known_issues.md`](known_issues.md) with
severity, status, and code path. Two are worth surfacing here as schema-level
gaps: (i) lower- and upper-bound redshift constraints (e.g., $z \leq 1.61$
for the lensed GRB 990123 case) cannot be cleanly represented in the current
`Redshift` schema, which models a point value with symmetric or asymmetric
error; and (ii) conditional or hypothetical measurements (e.g., the *putative*
host galaxy at $z \sim 0.2$–0.3 conditional on the lensing hypothesis in the
same circular) likewise have no representation.

**Concurrent-access requirement for the serving layer.** The extraction store
is opened in SQLite Write-Ahead-Logged (WAL) mode to permit concurrent reads
by the query-serving worker and writes by an asynchronous indexer. Without
WAL, an early test exhibited silent worker crashes under concurrent
`circex index` invocations.

## 6. Future Work

Three extensions are planned. *First*, completion of the four-way evaluation
described in Section 5, including a published per-field comparison table and
chart, and a written cost-projection document derived from $\geq$100 actual
Haiku and Sonnet runs. *Second*, an upstream pull request against
`nasa-gcn/gcn-schema` containing the extended `Photometry`, new
`SpectralLines`, and new `Classification` JSON Schema artifacts dumped by
`circex schema-dump`. *Third*, completion of the TypeScript LeanMCP shim and
deployment of the worker in a SkyPortal-adjacent context for end-to-end
validation of the query-tool surface against real consumer queries.

A longer-horizon question is whether the regex baseline, the Claude
extractor, and the Ollama extractor admit informative ensemble behavior on
fields where they disagree, particularly on the photometry tables: a high
agreement rate between a high-precision regex run and a high-recall LLM run
could be used to construct a confidence-weighted union without paying full
LLM cost on circulars where regex suffices.

## 7. Reproducibility

The full pipeline is open-source. The result reported in Figure 1 and Table 1
regenerates with one command after the reference data products have been
fetched:

```
circex eval --extractors regex --gold vidushi --max-circulars 500 \
  --report reports/eval_v1.md \
  --plot   reports/eval_v1.png \
  --plot-baseline vidushi-mistral
```

The pipeline currently consists of 269 unit and integration tests, all
passing under `ruff check` and `mypy --strict` on the package. CI runs on both
Windows and Ubuntu. The companion [README](../README.md) provides nine
worked-example recipes spanning single-circular extraction, batch extraction,
evaluation, serving, and the browser front end.

---

## Acknowledgments

This work directly builds on Sharma et al. (2025) and uses three data
products and the controlled vocabulary distributed by the NASA GCN and
SkyPortal projects. Reusable Python modules (SQLite/FTS5 schema, indexer
pipeline, event-name regex skeleton, GCN HTTP poller) were ported from the
`sjhend03/GCNMCP` prototype with attribution; modifications to those modules
are documented in the project README.

## References

- Sharma, V., Agarwala, R., Racusin, J. L., Singer, L. P., Barna, T., Burns,
  E., Coughlin, M. W., Dutko, D., Elliott, C., Gupta, R., Mahabal, A., &
  Mukund, N. (2026). *Large Language Model-driven Analysis of General
  Coordinates Network (GCN) Circulars.* The Astrophysical Journal Supplement
  Series, 283(1), 30. arXiv:2511.14858.
- NASA GCN Project. *gcn-schema.* `https://github.com/nasa-gcn/gcn-schema`.
- NASA GCN Project. *circulars-nlp-paper.*
  `https://github.com/nasa-gcn/circulars-nlp-paper`.
- SkyPortal Project. *timedomain-taxonomy.*
  `https://github.com/skyportal/timedomain-taxonomy`.
- Anthropic. *Claude API documentation.* `https://docs.anthropic.com`.
- Ollama Project. *Ollama.* `https://ollama.com`.
