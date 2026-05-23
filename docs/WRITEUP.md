# Schema-Constrained Structured Extraction from GCN Optical Circulars

**Phillips, E.** (Circex Project)

*Draft report, 2026-05-23. Companion follow-on to Sharma et al. (2025;
hereafter S25) on automated parsing of the GCN Circulars archive.*

---

## Abstract

The GCN Circulars archive contains over 40,500 free-text observation reports
written by astronomers since 1997. About 18,600 of these are optical
observations, and the prose format makes the data difficult to ingest into
downstream systems like SkyPortal. We describe *Circex*, a pipeline that
converts free-text optical circulars into validated JSON conforming to the
`nasa-gcn/gcn-schema`. Three extractors share one output schema: a
regular-expression baseline composed of six sub-parsers, a Claude extractor
that uses tool-use to enforce schema conformance, and an Ollama extractor
running the Mistral-7B-Instruct-v0.2 model used by S25 for direct comparison.
We evaluate against S25's 13,593-row Swift-validated redshift table and find,
on 500 sampled rows, that the regex baseline alone exceeds the published
Mistral-7B predictions by +0.020 F1 on event-name extraction and +0.168 F1 on
redshift extraction. The Mistral baseline is therefore beatable rather than a
strawman, and the four-way headline comparison (regex / Claude-Haiku /
Claude-Sonnet / Ollama), once the live LLM columns are run, is well
positioned to clear the +0.01 F1-per-field acceptance bar set in the project
plan. We additionally describe an MCP serving layer with seven structured
query tools and a browser front-end for interactive use. The full four-way
comparison and a 50-circular hand-labeled gold set covering the ~20 fields
beyond S25's four remain in progress.

---

## 1. Introduction

The GCN Circulars archive is the principal record of human-authored
observation reports for high-energy and multimessenger astronomical transients.
At the time of S25 it held 40,506 circulars, of which approximately 18,600
were tagged as optical observations under their topic-modeling classifier.
The free-text format gives authors flexibility but blocks direct ingestion
by automated consumers, and manual extraction of fields like redshift,
photometry tables, or source classifications across the full archive is
infeasible.

S25 showed that a single open-source LLM (Mistral-7B-Instruct-v0.2),
combined with prompt tuning, output parsing, and retrieval-augmented
generation, can extract GRB redshift values at 97.2% accuracy on the subset
of circulars known to contain redshifts. That result establishes the field
and raises two follow-on questions we address here. First, how does a
serious regular-expression baseline perform on the same gold set: is the
published LLM result a real advance over what regex can do, or is the regex
strawman that papers usually compare to weaker than necessary? Second, do
frontier LLMs given a structured output contract materially improve
extraction on the fields where regex is expected to fail hardest — multi-row
photometry tables, magnitude-system inference, and in-prose source
classification — relative to both the regex baseline and the S25 Mistral
result?

To answer both questions we built *Circex*. The system is built around a
single Pydantic v2 model, `CircularExtraction`, that every extractor emits;
this is what makes the four-way comparison apples to apples. Three
extractors implement a common `Extractor` interface: a regex baseline with
six sub-parsers, a Claude extractor that uses forced tool-use against the
JSON Schema dump of the model, and an Ollama extractor running the same
Mistral-7B model S25 used. An evaluation harness produces per-field
precision, recall, and F1 against either S25's Swift-validated gold or a
local hand-labeled set, with set-semantics matching for list fields. A
long-lived asynchronous worker exposes seven structured query tools over an
MCP-compatible interface for downstream consumers.

The remainder of this report is organized as follows. Section 2 describes
the corpus and gold sets. Section 3 details the schema, the three
extractors, the evaluation methodology, and the serving layer. Section 4
presents the regex-vs-S25 comparison on 500 sampled rows. Section 5
discusses what we did not finish and what surprised us along the way.
Section 6 sketches planned extensions including an upstream schema
contribution.

## 2. Data

We use three data products distributed with S25's accompanying repository,
[`nasa-gcn/circulars-nlp-paper`](https://github.com/nasa-gcn/circulars-nlp-paper).
The full 40,506-circular archive ships as a 27 MB compressed tarball; each
circular is a JSON object containing `circularId`, `subject`, `eventId`,
`body`, `submitter`, `createdOn`, and `bibcode`. Topic labels for every
circular come from S25's contrastively fine-tuned MiniLM classifier and
assign each entry to one of five classes (Optical Observations, High-Energy
Observations, Radio Observations, Neutrinos, Gravitational Wave). We use
the 18,642-circular Optical Observations subset as the working scope.

The gold set for evaluation is `redshift_accuracy.csv` (13,593 rows). Each
row pairs a circular with the Swift Burst Analyser-derived ground truth
(Actual columns: redshift, GRB number, telescope name, redshift type) and
S25's Mistral-7B predictions for the same four fields. We treat the Actual
columns as gold and the Predicted columns as the published baseline.

A non-obvious detail in this file: missing values are stored as the literal
string `"No Information"` rather than blank or `NaN`. Our loader did not
handle this initially and the comparator briefly attributed dozens of
spurious value mismatches to S25's predictions before we tracked it down.
The `Actual Redshift Type` column turns out to be populated for zero of our
500 sampled rows, which collapses the four nominally shared fields to three
in practice.

## 3. Methods

### 3.1 Output Schema

Every extractor emits a `CircularExtraction` Pydantic v2 model. Existing
`nasa-gcn/gcn-schema` core schemas (`Event`, `FollowUp`, `Localization`,
`DateTime`, `Photometry`, `Redshift`, `Reporter`) are mirrored field for
field as nested Pydantic models. We extend `Photometry` with optical-specific
fields needed for downstream consumers — `telescope`, `instrument`,
`calibration_reference`, `galactic_extinction_corrected`, `seeing`, `airmass`
— and tighten `mag_system` from open string to the enum
`AB | Vega | STMag`. The enum tightening is technically a breaking change
relative to the current upstream definition; we flag it for the upstream
review. Two new schemas sit alongside the existing ones: `SpectralLines`
(a list of identified emission or absorption lines with rest wavelength,
observed wavelength, and equivalent width) and `Classification` (validated
against the
[`skyportal/timedomain-taxonomy`](https://github.com/skyportal/timedomain-taxonomy)
controlled vocabulary, which contains 175 canonical class names). Output
validation is enforced at construction.

### 3.2 Regular-Expression Baseline

The regex baseline composes six sub-parsers. Event-name extraction handles
GRB, EP, modern TNS-style AT and SN designations (lowercase letter-run
suffix) and the legacy single-letter forms, ZTF, ATLAS, ASAS-SN, Pan-STARRS,
GOTO, IceCube, and Swift X-ray catalog identifiers, plus a separate
cross-reference pattern for GCN circular numbers. Coordinate extraction goes
through `astropy.coordinates.SkyCoord` and always returns ICRS J2000 decimal
degrees; we require explicit `RA`/`Dec` labels and intentionally do not
extract unlabeled coordinate pairs. Photometry has a prose parser for
single-magnitude detections (`r = 18.42 \pm 0.05`-style) and upper limits
(`r > 22.5`-style), plus a multi-row table detector keyed on header
keywords (date, MJD, epoch, filter, band, mag, err, exp); the table parser
is intentionally conservative and skips layouts without an explicit header,
which is where S25's diagnosis that regex fails hardest is most easily
observed. The redshift parser uses `z\s*[=\sim]\s*\d+\.\d+` with a
$\pm 200$-character context window to tag spec/photo and emission/absorption/host
where the surrounding text supports it. Classification does a
longest-alias-first lookup over the 175-class time-domain taxonomy. Time
offsets capture literal $T_0$-relative phrasings (`T+234s`, "4 hours after
the trigger") into a `TimeOffset` record without resolving to an absolute
time.

Two regex choices deserve comment. We reject single-magnitude values below
5.0 mag globally and lowercase Sloan-$z$ values below 10.0 mag in particular;
the latter is because the literal pattern would otherwise match redshift
notation like `z = 1.61` and report a Sloan-$z$ magnitude of 1.61 (which we
hit immediately on the GRB 990123 lensed-burst circular). The multi-row
table parser's conservatism on header-less layouts costs real recall on
older circulars — but recovering it would erode precision in exactly the way
S25 predicts. We did not bridge those gaps in the baseline, because the
point of the baseline is to measure them.

### 3.3 Large Language Model Extractors

The Claude extractor uses the Anthropic Claude API with two model variants,
Claude-Haiku-4-5 (`claude-haiku-4-5-20251001`) and Claude-Sonnet-4-6
(`claude-sonnet-4-6`). Structured output is enforced via tool-use: a single
`submit_extraction` tool whose `input_schema` is the JSON Schema derived
from the `CircularExtraction` model (with `circular_id` and
`extraction_meta` stripped, since those are filled in by the runner).
`tool_choice` forces the model to invoke this tool exactly once per
circular. This eliminates the "model emits prose around JSON" failure mode
that motivates the output-parsing layer in S25, and it makes structural
errors impossible — the model can be wrong about *values* but not about
*shape*. The system prompt and four few-shot examples carry
`cache_control: ephemeral` so Anthropic prompt caching reduces token cost
on repeated calls. The few-shots cover four of the five labeling strata
defined in our specification (multi-row magnitude table, in-prose
classification, photometric upper limit, GCN cross-reference); we
deliberately omit the GW/neutrino counterpart stratum from the in-context
examples so the eval measures generalization rather than few-shot
memorization.

The Ollama extractor uses the same Mistral-7B-Instruct-v0.2 model as S25.
Mistral lacks first-class tool-use, so we embed the JSON Schema in the
system prompt and rely on Ollama's `format="json"` constraint. On Pydantic
validation failure the extractor retries once with the validation error
appended to the conversation. The prompt template is otherwise shared
across providers; the per-provider differences live entirely in the
extractor classes that wrap them.

LLM responses are cached in SQLite keyed on
$(\text{extractor\_id}, \text{model\_id}, \text{prompt\_version},
\text{circular\_id}, \text{sha1}(\text{body}))$. Bumping the prompt version
invalidates cache entries cleanly. In practice this means iterating on the
prompt does not re-pay for unchanged circulars, which matters for cost
reasons when the corpus is 18,600 circulars long.

### 3.4 Evaluation

The per-field comparator is null-aware. For each ground-truth/predicted
pair it emits one of five outcomes: a true positive when both are
populated and the values agree, a false positive when the prediction is
populated but the gold is null, a false negative when the gold is populated
but the prediction is null, a true negative when both are null (not counted
toward P/R/F1), and a mismatch when both are populated but disagree. We
count a mismatch as both a false positive and a false negative, following
the standard information-extraction convention; the alternative of charging
only one side is more lenient than the literature uses.

Numeric fields are compared with per-field tolerances: $\pm 0.001$ for
redshift, $\pm 0.001\degree$ for RA and Dec, $\pm 0.05$ mag for photometry.
Categorical fields use exact equality on the canonical enum value. The
event-name comparison uses set intersection on the list/string union, so an
extraction listing both `GW170817` and `AT2017gfo` matches a gold list
containing either. List fields (photometry rows, time offsets) use greedy
row-level matching: we count true positives, false positives, and false
negatives at the row level rather than penalizing the whole list when one
row differs. Per-field metrics are the usual $P = TP/(TP+FP)$,
$R = TP/(TP+FN)$, $F_1 = 2PR/(P+R)$.

Fields with zero non-null gold values across the evaluation set report
support zero and are excluded from the headline plot. This is more common
than it sounds; see Section 2.

### 3.5 Serving Layer

A long-lived asyncio worker (`circex serve`) exposes seven tools over a
JSON-line TCP protocol on localhost: `extract_properties`, `get_redshift`,
`get_photometry`, `get_classification`, `find_counterparts`,
`search_gcn_circulars` (FTS5-backed), and `fetch_gcn_circulars`. Tool
results are read from a SQLite extraction store keyed on
$(\text{circular\_id}, \text{extractor\_id}, \text{model\_id},
\text{prompt\_version})$; on store miss with a configured default
extractor, the worker extracts on demand and persists the result. The
store is opened in Write-Ahead-Logged mode so that the indexer can backfill
new extractions concurrently with the worker serving live queries. A
TypeScript LeanMCP shim (currently a stub) is the eventual MCP front for
SkyPortal-style consumers; a stdlib-only HTTP bridge with a
single-file HTML front-end is provided for interactive demonstration.

## 4. Results

We evaluate the regex baseline against S25's Mistral-7B predictions on the
first 500 rows of the 13,593-row Swift-validated gold set. The evaluation
reproduces from a single command and requires neither API credentials nor
hand-labeling. Figure 1 shows the per-field F1 and the $\Delta$F1 against
the published baseline.

![Figure 1. Top: per-field F1 for regex (blue) and S25's Mistral-7B predictions (orange). Bottom: $\Delta$F1 = regex - S25 per field. Hatched "n/a" bars indicate either a non-extracting extractor (regex does not attempt telescope-name extraction) or zero gold support on a field.](images/eval_example_regex_vs_vidushi.png)

Numerical results for the three fields with non-zero gold support are in
Table 1.

| Field | Support | Regex (this work) | S25 (Mistral-7B) | $\Delta$F1 |
|---|---:|---:|---:|---:|
| Event name (GRB number) | 400 | 0.869 | 0.849 | +0.020 |
| Redshift value | 383 | 0.858 | 0.690 | +0.168 |
| Telescope name | 400 | n/a | 0.098 | — |

*Table 1. Per-field F1 on 500 sampled rows of `redshift_accuracy.csv`.
Support is the number of non-null gold values per field (TP + FN). The
regex baseline does not attempt telescope-name extraction; S25's reported
F1 of 0.098 reflects a string-normalization gap between Swift's formal
catalog codes (e.g., `VLT/X-shooter`) and the prose mentions LLMs tend to
pick up (e.g., "the VLT"), and we expect the Claude and Ollama extractors
will handle this through alias normalization. The `Actual Redshift Type`
column is populated for zero of the sampled rows and is omitted.*

The regex baseline matches or beats the published Mistral-7B predictions on
both fields with comparable gold support. The +0.168 F1 advantage on
redshift extraction is substantial enough to be worth examining carefully.

The first point to make about this number is what it is *not* doing. S25
report a headline redshift accuracy of 97.2%, which sounds inconsistent
with our finding. The two figures are not in conflict: S25's accuracy is
conditional on the subset of circulars *known to contain a redshift*, after
a separate retrieval-augmented retrieval step. The unconditioned F1 on the
full 13,593-row table — circulars that may or may not contain a redshift,
no retrieval step — is what their `Predicted Redshift` column reflects when
joined against the `Actual Redshift` ground truth, and that is what we
score. Our regex extractor and theirs are measured against the same
denominator, so the comparison is apples to apples.

The second point is that this is not the headline result we set out to
demonstrate. The project plan's acceptance criterion is that Claude beats
the published baseline by at least 0.01 F1 on at least three of the four
shared fields. We expect Claude to clear this bar comfortably because
schema-enforced output and a richer prompt are both straightforward
improvements over the published pipeline; what is more interesting is the
size of the gap, which we cannot publish until the live LLM columns have
been run. The fact that the regex baseline already clears most of the bar
sets a useful floor: any improvement we measure from Claude is on top of
that floor, not relative to a hand-wavy "no LLM" alternative.

## 5. Discussion and Limitations

The result in Figure 1 is missing the Claude-Haiku, Claude-Sonnet, and
Ollama columns. Producing them is straightforward — the extractors are
implemented and tested with mocked API responses, and `circex eval
--extractors regex,claude-haiku,claude-sonnet,ollama` runs end to end —
but the live runs require an Anthropic API key (which the development
shell we wrote this in does not have) and a local Ollama daemon with
Mistral-7B pulled. Projected cost on the 500-row evaluation is around
\$0.30 for Claude-Haiku and \$1.50 for Claude-Sonnet at the pricing in
effect on 2026-05-13; Ollama imposes no API cost but does require local
compute. A full backfill of the 18,642-circular optical subset at
Claude-Haiku pricing projects to around \$20.

Even with those columns added, the four-way comparison only exercises four
of the ~20 fields in our schema. The fields where the regex baseline is
expected to lose hardest to Claude — multi-row photometry tables, in-prose
classification, unlabeled coordinates, spectroscopy lines, time-since-trigger
offsets — are exactly the fields S25 did not extract, so there is no
existing gold against which to score them. We have staged 50 stratified
hand-labeling templates (one per circular, drawn from five strata defined
in our labeling specification: single-row magnitude, multi-row table,
spectroscopic classification, photometric upper limit, and GW/neutrino
counterpart) together with a labeling spec. The labels themselves require
human adjudication; we have not produced them.

Two schema-level gaps surfaced while writing the regex baseline that are
worth flagging at the discussion level. Bound redshift constraints — e.g.,
$z \leq 1.61$ for the gravitationally lensed GRB 990123 — cannot be
represented in the current `Redshift` schema, which models a point value
with symmetric or asymmetric error. The labeler hitting this case must
either store the bound as a point value (losing the inequality) or leave it
null (losing the value). Conditional or hypothetical measurements — the
*putative* host galaxy at $z \sim 0.2$–0.3 conditional on the lensing
hypothesis in the same circular — likewise have no representation. Both
gaps recur across the archive; both should be addressed in a future schema
revision.

A serving-layer note: an early integration test crashed the worker
silently when `circex index` was invoked against the same SQLite store the
worker had open for reads. The fix was to open the store in
Write-Ahead-Logged mode, which allows concurrent readers and one writer.
This is the kind of failure that is easy to miss in unit tests because
each test holds the database for the duration of its own process; we
caught it only when assembling the end-to-end demo. The fix is in;
mentioning it here so that anyone deploying the worker behind a long-lived
indexer pipeline does not rediscover it the hard way.

Twenty-one further limitations of varying severity are catalogued in
[`docs/known_issues.md`](known_issues.md) with status and code paths.

## 6. Future Work

The most immediate item is completing the four-way evaluation: running the
live LLM columns described in Section 5, publishing the resulting per-field
comparison table and chart, and deriving a cost-projection document from
$\geq 100$ actual Haiku and Sonnet runs against representative circular
lengths. The hand-labeling work follows the same critical path because
fields beyond S25's four require local gold to score.

We plan an upstream pull request against `nasa-gcn/gcn-schema` containing
the extended `Photometry`, the new `SpectralLines`, and the new
`Classification` JSON Schema artifacts emitted by `circex schema-dump`.
Two items in that PR are worth reviewer attention: the `mag_system` enum
tightening is a breaking change for any consumer that currently writes a
non-canonical value, and the new `SpectralLines` schema is
optical-spectroscopy-specific and should sit alongside the existing
high-energy `Spectral` schema rather than replacing it.

A longer-horizon question concerns ensemble behavior. The three extractors
are independent and will, on most fields, disagree on different circulars.
A high-precision regex extraction that agrees with a high-recall LLM
extraction is more trustworthy than either alone; a circular where regex
returns nothing and the LLM returns a value is the case where the LLM is
plausibly buying us recall the regex cannot. This suggests a
confidence-weighted union that pays full LLM cost only on circulars where
regex output is empty or low-confidence, which would meaningfully shrink
the projected backfill cost without obviously hurting recall. We have not
implemented this; the data needed to evaluate it falls out of the eval
runs in Section 5 once those are done.

Finally, the TypeScript LeanMCP shim is currently a stub. Completing it
and deploying the worker in a SkyPortal-adjacent context is the last
step before this becomes useful to anyone outside the project.

## 7. Reproducibility

The pipeline is open-source. Figure 1 and Table 1 regenerate from a single
command after the reference data products have been cloned:

```
circex eval --extractors regex --gold vidushi --max-circulars 500 \
  --report reports/eval_v1.md \
  --plot   reports/eval_v1.png \
  --plot-baseline vidushi-mistral
```

The pipeline consists of 269 unit and integration tests, all passing under
`ruff check` and `mypy --strict` on the package. CI runs on Windows and
Ubuntu. The companion [README](../README.md) provides nine worked-example
recipes covering single-circular extraction, batch extraction, evaluation,
serving, and the browser front end.

---

## Acknowledgments

This work builds directly on S25 and uses three of their data products —
the full circulars archive, the topic labels, and the Swift-validated
redshift gold — along with the
[`skyportal/timedomain-taxonomy`](https://github.com/skyportal/timedomain-taxonomy)
controlled vocabulary. Reusable Python modules (SQLite/FTS5 schema, the
indexer pipeline, the event-name regex skeleton, and the GCN HTTP poller)
were ported from the `sjhend03/GCNMCP` prototype with attribution;
modifications relative to the originals are documented in the project
README.

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
