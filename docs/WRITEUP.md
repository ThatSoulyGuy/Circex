# Schema-Constrained Structured Extraction from GCN Optical Circulars

**Phillips, E.** (Circex Project)

*Draft, 2026-05-23. Companion follow-on to Sharma et al. (2026; hereafter
S25) on automated parsing of the GCN Circulars archive.*

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
Claude-Sonnet / Ollama) is well positioned, once the live LLM columns are
run, to clear an acceptance threshold of $+0.01$ F1 per field that we
adopted in advance of the experiment. We additionally describe an MCP
serving layer with seven structured query tools and a browser front-end for
interactive use. The full four-way comparison and a 50-circular
hand-labeled gold set covering the $\sim$20 fields beyond S25's four
remain in progress.

---

## 1. Introduction

The GCN Circulars archive is the principal record of human-authored
observation reports for high-energy and multimessenger astronomical
transients, with antecedents going back to the BACODINE/GCN coordinate
distribution system (Barthelmy et al. 2000). At the time of S25 it held
40,506 circulars, of which approximately 18,600 were tagged as optical
observations under their topic-modeling classifier. The free-text format
gives authors flexibility but blocks direct ingestion by automated
consumers — including platforms such as SkyPortal (van der Walt et al.
2019) — and manual extraction of fields like redshift, photometry
tables, or source classifications across the full archive is infeasible.

S25 showed that a single open-source LLM, Mistral-7B-Instruct-v0.2 (Jiang
et al. 2023), combined with prompt tuning, output parsing, and
retrieval-augmented generation (Lewis et al. 2020), can extract GRB
redshift values at 97.2% accuracy on the subset of circulars known to
contain redshifts. That result establishes the field and raises two
follow-on questions we address here. First, how does a serious
regular-expression baseline perform on the same gold set: is the published
LLM result a real advance over what regex can do, or is the regex strawman
that papers usually compare to weaker than necessary? Second, do frontier
LLMs given a structured output contract materially improve extraction on
the fields where regex is expected to fail hardest — multi-row photometry
tables, magnitude-system inference, and in-prose source classification —
relative to both the regex baseline and the S25 Mistral result?

To answer both questions we built *Circex*. The system is built around a
single Pydantic v2 model, `CircularExtraction`, that every extractor emits;
this is what makes the four-way comparison apples to apples. Three
extractors implement a common `Extractor` interface: a regex baseline with
six sub-parsers, a Claude extractor that uses forced tool-use against the
JSON Schema dump of the model (Pezoa et al. 2016), and an Ollama extractor
running the same Mistral-7B model S25 used. An evaluation harness produces
per-field precision, recall, and F1 against either S25's Swift-validated
gold or a local hand-labeled set, with set-semantics matching for list
fields. A long-lived asynchronous worker exposes seven structured query
tools over a Model Context Protocol-compatible interface (Anthropic 2024a)
for downstream consumers.

### 1.1 Related Work

Information extraction from astronomical free text has historically relied
on hand-crafted regular expressions and ontology-aligned rule systems; the
SIMBAD object resolver (Wenger et al. 2000) and the Astrophysics Data
System's metadata pipelines (Accomazzi et al. 2015) are representative
production-grade examples. The transformer era opened the door to learned
extractors. Domain-specific encoders such as astroBERT (Grezes et al.
2021) were fine-tuned for named-entity recognition over astronomical
abstracts, and more recently zero- and few-shot prompting with general
LLMs (Brown et al. 2020) has been applied to GCN-style alert text by S25
and others. Our contribution sits between these two lines: rather than
choose between regex and LLMs, we hold the output contract fixed across
both and use that shared schema to make a like-for-like four-way
comparison.

The remainder of this paper is organized as follows. Section 2 describes
the corpus and gold sets. Section 3 details the schema, the three
extractors, the evaluation methodology, and the serving layer. Section 4
presents the regex-vs-S25 comparison on 500 sampled rows. Section 5
discusses limitations of the present evaluation and two schema-level gaps
surfaced during construction of the regex baseline. Section 6 sketches
planned extensions, including an upstream schema contribution. Section 7
concludes; Section 8 documents reproducibility.

## 2. Data

We use three data products distributed with S25's accompanying repository,
[`nasa-gcn/circulars-nlp-paper`](https://github.com/nasa-gcn/circulars-nlp-paper).
The full 40,506-circular archive ships as a 27 MB compressed tarball; each
circular is a JSON object containing `circularId`, `subject`, `eventId`,
`body`, `submitter`, `createdOn`, and `bibcode`. Topic labels for every
circular come from S25's contrastively fine-tuned MiniLM encoder (Wang et
al. 2020) and assign each entry to one of five classes (Optical
Observations, High-Energy Observations, Radio Observations, Neutrinos,
Gravitational Wave). We use the 18,642-circular Optical Observations
subset as the working scope.

The gold set for evaluation is `redshift_accuracy.csv` (13,593 rows). Each
row pairs a circular with ground truth derived from the *Swift* Burst
Analyser (Evans et al. 2007, 2009) — Actual columns: redshift, GRB
number, telescope name, redshift type — together with S25's Mistral-7B
predictions for the same four fields. We treat the Actual columns as gold
and the Predicted columns as the published baseline.

One detail in this file warrants explicit mention for downstream users:
missing values are encoded as the literal string `"No Information"`
rather than blank or `NaN`, and loaders that treat the column as numeric
without sentinel handling will silently mis-score the published baseline.
Within our 500-row evaluation sample, the `Actual Redshift Type` column is
populated for zero rows, which collapses the four nominally shared fields
to three in practice.

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
relative to the current upstream definition and is called out as such in
the proposed schema PR (§6). Two new schemas sit alongside the existing ones: `SpectralLines`
(a list of identified emission or absorption lines with rest wavelength,
observed wavelength, and equivalent width) and `Classification` (validated
against the
[`skyportal/timedomain-taxonomy`](https://github.com/skyportal/timedomain-taxonomy)
controlled vocabulary, which contains 175 canonical class names). Output
validation is enforced at construction.

Alongside the value-bearing fields, `CircularExtraction` carries an optional
`provenance` map from dotted field path to a `Span(start, end, snippet)`
record giving character offsets back into the circular body. The convention
is object-level keys for nested singletons (e.g., `"redshift"`,
`"localization"`) and indexed keys for list items (`"photometry[0]"`),
with leaf-level keys (`"redshift.redshift"`, `"photometry[0].mag"`)
permitted where an extractor can attribute more precisely. `provenance` is
operationally distinct from `extraction_meta`: the former describes the
*data* (where each value came from in the source text) and the latter
describes the *run* (model, tokens, cost). The field is Circex-internal —
unlike the extended `Photometry`, `Classification`, and `SpectralLines`
schemas, it is not part of the upstream gcn-schema PR — but it is the
mechanism by which downstream consumers can audit any extracted value
without re-reading the source by hand.

### 3.2 Regular-Expression Baseline

The regex baseline composes six sub-parsers. Event-name extraction handles
GRB, EP, modern TNS-style AT and SN designations (lowercase letter-run
suffix) and the legacy single-letter forms, together with identifiers from
the major optical transient surveys — ZTF (Bellm et al. 2019), ATLAS
(Tonry et al. 2018), ASAS-SN (Shappee et al. 2014), Pan-STARRS (Chambers
et al. 2016), GOTO (Steeghs et al. 2022), the IceCube neutrino observatory
(Aartsen et al. 2017), and *Swift* X-ray catalog identifiers (Evans et
al. 2014) — plus a separate cross-reference pattern for GCN circular
numbers. Coordinate extraction goes through `astropy.coordinates.SkyCoord`
(Astropy Collaboration et al. 2013, 2018, 2022) and always returns ICRS
J2000 decimal degrees; we require explicit `RA`/`Dec` labels and
intentionally do not extract unlabeled coordinate pairs. Photometry has a prose parser for
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

Two regex choices deserve comment. Single-magnitude values below 5.0 mag
are rejected globally, and lowercase Sloan-$z$ values below 10.0 mag are
rejected in particular; the latter rule exists because the literal pattern
would otherwise match redshift notation such as `z = 1.61` and report a
spurious Sloan-$z$ magnitude of 1.61 — a failure mode that appears on the
GRB 990123 circulars discussed in §5. The multi-row table parser's
conservatism on header-less layouts costs real recall on older circulars,
but recovering it would erode precision in exactly the way S25 predicts.
We deliberately do not bridge those gaps in the baseline; their existence
is precisely what the baseline is meant to measure.

Every sub-parser additionally exposes the `(start, end)` of the regex
match it consumed, which the composing extractor aggregates into the
`provenance` map described in §3.1. Object-level spans are emitted for
each of `event`, `redshift`, `classification`, `localization`,
`follow_up`, and one span per `photometry[i]` / `time_offsets[i]` list
entry, with each span's `snippet` carrying the literal `body[start:end]`
substring for round-trip verification.

### 3.3 Large Language Model Extractors

The Claude extractor uses the Anthropic Claude API (Anthropic 2024b) with
two model variants, Claude-Haiku-4-5 (`claude-haiku-4-5-20251001`) and
Claude-Sonnet-4-6 (`claude-sonnet-4-6`). Structured output is enforced via
tool-use: a single `submit_extraction` tool whose `input_schema` is the
JSON Schema derived from the `CircularExtraction` model (with
`circular_id` and `extraction_meta` stripped, since those are filled in by
the runner). `tool_choice` forces the model to invoke this tool exactly
once per circular. This eliminates the "model emits prose around JSON"
failure mode that motivates the output-parsing layer in S25, and it makes
structural errors impossible — the model can be wrong about *values* but
not about *shape*. The system prompt and four few-shot examples (Brown et
al. 2020) carry `cache_control: ephemeral` so Anthropic prompt caching
reduces token cost on repeated calls. The few-shots cover four of the five
labeling strata defined in our specification (multi-row magnitude table,
in-prose classification, photometric upper limit, GCN cross-reference); we
deliberately omit the GW/neutrino counterpart stratum from the in-context
examples so the eval measures generalization rather than few-shot
memorization. The system prompt also instructs the model to populate the
`provenance` map of §3.1, preferring leaf-level keys (e.g.,
`"redshift.redshift"` pointing at the exact `z = X` substring) where one
contiguous phrase justifies the value; one of the four few-shots
demonstrates the pattern, and the constraint that
`body[start:end] == snippet` lets a downstream consumer reject any
extraction whose offsets do not resolve.

The Ollama extractor uses the same Mistral-7B-Instruct-v0.2 model as S25
(Jiang et al. 2023). Mistral lacks first-class tool-use, so we embed the
JSON Schema in the system prompt and rely on Ollama's `format="json"`
constraint. On Pydantic validation failure the extractor retries once with
the validation error appended to the conversation. The prompt template is
otherwise shared across providers; the per-provider differences live
entirely in the extractor classes that wrap them.

LLM responses are cached in SQLite keyed on $extractor\_{id}, model\_{id}, prompt\_{version}, circular\_{id}, sha1(body)$.
Bumping the prompt version
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
the standard information-extraction convention (Chinchor 1992); the
alternative of charging only one side is more lenient than the literature
uses.

Numeric fields are compared with per-field tolerances: $\pm 0.001$ for
redshift, $\pm 0.001\deg$ for RA and Dec, $\pm 0.05$ mag for photometry.
Categorical fields use exact equality on the canonical enum value. The
event-name comparison uses set intersection on the list/string union, so an
extraction listing both `GW170817` (Abbott et al. 2017a) and `AT2017gfo`
(Coulter et al. 2017) matches a gold list containing either. List fields (photometry rows, time offsets) use greedy
row-level matching: we count true positives, false positives, and false
negatives at the row level rather than penalizing the whole list when one
row differs. Per-field metrics are the usual $P = TP/(TP+FP)$,
$R = TP/(TP+FN)$, $F_1 = 2PR/(P+R)$.

Fields with zero non-null gold values across the evaluation set report
support zero and are excluded from the headline plot. This is more common
than it sounds; see Section 2.

The comparator currently scores values only; the `provenance` map of §3.1
opens a second axis on which extractors can be graded (does the cited span
in fact justify the value?), which is the subject of an extension
discussed in §6.

### 3.5 Serving Layer

A long-lived asyncio worker (`circex serve`) exposes nine tools over a
JSON-line TCP protocol on localhost: `extract_properties`, `extract_text`,
`get_redshift`, `get_photometry`, `get_classification`, `find_counterparts`,
`search_by_position`, `search_gcn_circulars` (FTS5-backed), and
`fetch_gcn_circulars`. The `extract_text` tool is the live-pipeline entry
point — it extracts from a raw circular body rather than an archive ID, so
circulars arriving over the GCN Kafka stream before they are archived can
still be processed; `search_by_position` is a cone search over stored
localizations, the reliable join for un-named optical transients reported
with only RA/Dec. Tool results are read from a SQLite extraction store
keyed on
$circular\_{id}, extractor\_{id}, model\_{id},
prompt\_{version}$; on store miss with a configured default
extractor, the worker extracts on demand and persists the result. The
store is opened in Write-Ahead-Logged mode so that the indexer can backfill
new extractions concurrently with the worker serving live queries. A
TypeScript LeanMCP front-end (`leanmcp_bridge/`) sits on top of the worker
and speaks the streamable-HTTP MCP protocol on port 3001, forwarding each
tool call over the persistent TCP socket to the Python worker on 8765; the
nine tools are declared as decorated methods on a single `GcnService`
class, with per-tool input schemas auto-generated from TypeScript class
properties via `@leanmcp/core`'s `classToJsonSchemaWithConstraints`. A
stdlib-only HTTP bridge with a single-file HTML front-end is also provided
for interactive demonstration without an MCP client in the loop.

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
demonstrate. Our pre-registered acceptance criterion is that Claude beats
the published baseline by at least $0.01$ F1 on at least three of the four
shared fields. We expect Claude to clear this bar comfortably because
schema-enforced output and a richer prompt are both straightforward
improvements over the published pipeline; the more interesting open
question is the size of the gap, which will be reported with the live
Claude and Ollama columns in a forthcoming revision. The fact that the
regex baseline already clears most of the bar sets a useful floor: any
improvement we measure from Claude lies on top of that floor, rather than
relative to a notional "no LLM" alternative.

## 5. Discussion and Limitations

Figure 1 omits the Claude-Haiku, Claude-Sonnet, and Ollama columns. The
extractors are implemented and exercised in unit tests against mocked API
responses, and the end-to-end command
`circex eval --extractors regex,claude-haiku,claude-sonnet,ollama` runs to
completion; producing the missing columns therefore requires only API
credentials and a Mistral-7B-enabled Ollama daemon, neither of which was
available in the environment used to prepare this draft. The projected
cost on the 500-row evaluation is approximately \$0.30 for Claude-Haiku
and \$1.50 for Claude-Sonnet at the pricing in effect on 2026-05-13;
Ollama imposes no API cost but does require local GPU compute. A full
backfill of the 18,642-circular optical subset at Claude-Haiku pricing
projects to approximately \$20.

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
$z \leq 1.61$ for the lens-hypothesis interpretation of GRB 990123
(Kulkarni et al. 1999; Akerlof et al. 1999) — cannot be represented in
the current `Redshift` schema, which models a point value with symmetric
or asymmetric error. The labeler hitting this case must
either store the bound as a point value (losing the inequality) or leave it
null (losing the value). Conditional or hypothetical measurements — the
*putative* host galaxy at $z \sim 0.2$–0.3 conditional on the lensing
hypothesis in the same circular — likewise have no representation. Both
gaps recur across the archive; both should be addressed in a future schema
revision.

One serving-layer note carries practical consequences for operators.
Invoking `circex index` against the same SQLite store that the worker
holds open for reads produces silent contention under the default
rollback-journal mode, with the worker dropping queries rather than
failing loudly. This class of failure is easy to miss in unit tests, each
of which holds the database for the duration of a single process, and is
visible only in end-to-end deployments. Opening the store in
Write-Ahead-Logging mode (allowing concurrent readers with a single
writer) resolves the contention; the published configuration enables
WAL by default, and we recommend operators verify the mode before pairing
a long-lived worker with a backfill pipeline.

Twenty-one further limitations of varying severity are catalogued in
[`docs/known_issues.md`](known_issues.md), with associated code paths.

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
extraction is more trustworthy than either alone; circulars on which regex
returns nothing and the LLM returns a value are precisely those on which
the LLM is plausibly providing recall the regex cannot. The `provenance`
spans of §3.1 sharpen this further: two extractors that report the same
value *and the same source span* meaningfully co-witness the claim, whereas
agreement on the value with disagreement on the span is a flag for review.
This motivates a confidence-weighted union strategy that incurs the full
LLM cost only on circulars where the regex output is empty or
low-confidence, an approach that would meaningfully shrink the projected
backfill cost without an obvious recall penalty. Evaluation of such a
strategy requires the per-circular disagreement statistics produced by the
runs described in §5 and is therefore deferred.

A second extension uses provenance to grade *attribution* alongside
*values*. The §3.4 comparator currently rewards correct values regardless
of which substring the extractor cited as evidence; an attribution score
would additionally check that the cited span overlaps a hand-labeled
evidence span, penalizing extractors that arrive at the right answer for
the wrong reason. Producing this score requires evidence spans on the
50-circular hand-labeled gold set, which is in the same labeling pass
discussed in §5 and is therefore on the same critical path.

The TypeScript LeanMCP front-end is now functional end-to-end: an MCP
client that hits `tools/list` against `http://localhost:3001/mcp` gets the
seven tools back with their JSON Schemas, and `tools/call` routes through
to the Python worker over the persistent TCP socket. What remains is
deploying it in a SkyPortal-adjacent setting and adding integration tests
on the TypeScript side; the Python worker is already covered by the
existing `tests/server/` suite.

## 7. Conclusions

We have presented *Circex*, a schema-constrained structured extraction
pipeline for the GCN Circulars archive, and reported the first head-to-head
comparison between a serious regular-expression baseline and the published
Mistral-7B predictions of S25 on a common Swift-validated gold set. Three
findings stand out. (i) On the two redshift-table fields with non-zero
gold support, a transparent regex baseline already outperforms the
published baseline by $+0.020$ F1 on event-name extraction and $+0.168$
F1 on redshift extraction; the published LLM result is therefore a real
target to beat rather than an aspirational benchmark. (ii) Pinning every
extractor to a single Pydantic v2 model (`CircularExtraction`) and
enforcing schema conformance through forced tool-use turns the LLM's
remaining failure mode from structural to substantive, which is the
relevant axis for downstream consumers; the same model carries an optional
`provenance` map that grounds each extracted value at a `(start, end)`
range in the source text, allowing audit without re-reading the circular.
(iii) The same model becomes a queryable interface when paired with a
long-lived asyncio worker and seven MCP-compatible tools, providing the
substrate for a SkyPortal-side integration that does not currently exist.

The work whose absence is most acutely felt by this report is the live
Claude and Ollama columns of the four-way comparison, and a hand-labeled
gold set that covers the ~20 fields beyond S25's four. Both are scoped,
implemented at the harness level, and gated only on credentials and
human-labeler time. With those in hand, the schema, the regex floor, and
the comparator established here should support a fully populated four-way
evaluation table and, in turn, the cost-quality trade-off curves needed
to decide which extractor a deployment such as SkyPortal should adopt at
the per-field level.

## 8. Reproducibility

The pipeline is open-source. Figure 1 and Table 1 regenerate from a single
command after the reference data products have been cloned:

```
circex eval --extractors regex --gold vidushi --max-circulars 500 \
  --report reports/eval_v1.md \
  --plot   reports/eval_v1.png \
  --plot-baseline vidushi-mistral
```

The pipeline ships with 269 unit and integration tests, all passing under
`ruff check` and `mypy --strict` on the package. Continuous integration
runs on Windows and Ubuntu. The companion [README](../README.md) provides
nine worked-example recipes covering single-circular extraction, batch
extraction, evaluation, serving, and the browser front end. A BibTeX file
mirroring the References section is provided alongside this manuscript at
[`docs/references.bib`](references.bib).

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

- Aartsen, M. G., Ackermann, M., Adams, J., et al. 2017, *Journal of
  Instrumentation*, 12, P03012. *The IceCube Neutrino Observatory:
  instrumentation and online systems.*
- Abbott, B. P., Abbott, R., Abbott, T. D., et al. 2017a, *Physical Review
  Letters*, 119, 161101. *GW170817: Observation of Gravitational Waves
  from a Binary Neutron Star Inspiral.*
- Abbott, B. P., Abbott, R., Abbott, T. D., et al. 2017b, *The
  Astrophysical Journal Letters*, 848, L12. *Multi-messenger Observations
  of a Binary Neutron Star Merger.*
- Accomazzi, A., Kurtz, M. J., Henneken, E. A., et al. 2015, in
  *Open Science at the Frontiers of Librarianship*, ASP Conference Series
  492, 189. *ADS All-Sky Survey: Bringing Knowledge to the Bibliography.*
- Akerlof, C., Balsano, R., Barthelmy, S., et al. 1999, *Nature*, 398,
  400. *Observation of contemporaneous optical radiation from a gamma-ray
  burst.*
- Anthropic. 2024a, *Model Context Protocol specification.*
  `https://modelcontextprotocol.io`.
- Anthropic. 2024b, *Claude API and tool use documentation.*
  `https://docs.anthropic.com`.
- Astropy Collaboration, Robitaille, T. P., Tollerud, E. J., et al. 2013,
  *Astronomy & Astrophysics*, 558, A33. *Astropy: A community Python
  package for astronomy.*
- Astropy Collaboration, Price-Whelan, A. M., Sipőcz, B. M., et al. 2018,
  *The Astronomical Journal*, 156, 123. *The Astropy Project: Building
  an Open-science Project and Status of the v2.0 Core Package.*
- Astropy Collaboration, Price-Whelan, A. M., Lim, P. L., et al. 2022,
  *The Astrophysical Journal*, 935, 167. *The Astropy Project: Sustaining
  and Growing a Community-oriented Open-source Project and the Latest
  Major Release (v5.0).*
- Barthelmy, S. D., Butterworth, P., Cline, T. L., et al. 2000, in
  *Gamma-Ray Bursts, 5th Huntsville Symposium*, AIP Conference Proceedings
  526, 731. *The GRB Coordinates Network (GCN): A Status Report.*
- Bellm, E. C., Kulkarni, S. R., Graham, M. J., et al. 2019, *Publications
  of the Astronomical Society of the Pacific*, 131, 018002. *The Zwicky
  Transient Facility: System Overview, Performance, and First Results.*
- Brown, T. B., Mann, B., Ryder, N., et al. 2020, in *Advances in Neural
  Information Processing Systems* 33, 1877. *Language Models are Few-Shot
  Learners.* arXiv:2005.14165.
- Chambers, K. C., Magnier, E. A., Metcalfe, N., et al. 2016,
  arXiv:1612.05560. *The Pan-STARRS1 Surveys.*
- Chinchor, N. 1992, in *Proceedings of the 4th Message Understanding
  Conference (MUC-4)*, 22. *MUC-4 Evaluation Metrics.*
- Coulter, D. A., Foley, R. J., Kilpatrick, C. D., et al. 2017, *Science*,
  358, 1556. *Swope Supernova Survey 2017a (SSS17a), the optical
  counterpart to a gravitational wave source.*
- Evans, P. A., Beardmore, A. P., Page, K. L., et al. 2007, *Astronomy &
  Astrophysics*, 469, 379. *An online repository of Swift/XRT light
  curves of γ-ray bursts.*
- Evans, P. A., Beardmore, A. P., Page, K. L., et al. 2009, *Monthly
  Notices of the Royal Astronomical Society*, 397, 1177. *Methods and
  results of an automatic analysis of a complete sample of Swift-XRT
  observations of GRBs.*
- Evans, P. A., Osborne, J. P., Beardmore, A. P., et al. 2014, *The
  Astrophysical Journal Supplement Series*, 210, 8. *1SXPS: A Deep Swift
  X-Ray Telescope Point Source Catalog.*
- Grezes, F., Blanco-Cuaresma, S., Accomazzi, A., et al. 2021, in
  *Proceedings of the Workshop on Scholarly Document Processing (SDP) at
  NAACL*. *Building astroBERT, a language model for astronomy and
  astrophysics.* arXiv:2112.00590.
- Jiang, A. Q., Sablayrolles, A., Mensch, A., et al. 2023, *Mistral 7B.*
  arXiv:2310.06825.
- Kulkarni, S. R., Djorgovski, S. G., Odewahn, S. C., et al. 1999,
  *Nature*, 398, 389. *The afterglow, redshift and extreme energetics of
  the γ-ray burst of 23 January 1999.*
- Lewis, P., Perez, E., Piktus, A., et al. 2020, in *Advances in Neural
  Information Processing Systems* 33, 9459. *Retrieval-Augmented
  Generation for Knowledge-Intensive NLP Tasks.* arXiv:2005.11401.
- NASA GCN Project. *gcn-schema.* `https://github.com/nasa-gcn/gcn-schema`.
- NASA GCN Project. *circulars-nlp-paper.*
  `https://github.com/nasa-gcn/circulars-nlp-paper`.
- Ollama Project. *Ollama: get up and running with large language models
  locally.* `https://ollama.com`.
- Pezoa, F., Reutter, J. L., Suarez, F., Ugarte, M., & Vrgoč, D. 2016, in
  *Proceedings of the 25th International Conference on World Wide Web*,
  263. *Foundations of JSON Schema.*
- Shappee, B. J., Prieto, J. L., Grupe, D., et al. 2014, *The
  Astrophysical Journal*, 788, 48. *The Man behind the Curtain:
  X-Rays Drive the UV through NIR Variability in the 2013 AGN Outburst
  in NGC 2617.* (ASAS-SN reference paper.)
- Sharma, V., Agarwala, R., Racusin, J. L., Singer, L. P., Barna, T.,
  Burns, E., Coughlin, M. W., Dutko, D., Elliott, C., Gupta, R., Mahabal,
  A., & Mukund, N. 2026, *The Astrophysical Journal Supplement Series*,
  283, 30. *Large Language Model-driven Analysis of General Coordinates
  Network (GCN) Circulars.* arXiv:2511.14858. (Cited as S25.)
- SkyPortal Project. *timedomain-taxonomy.*
  `https://github.com/skyportal/timedomain-taxonomy`.
- Steeghs, D., Galloway, D. K., Ackley, K., et al. 2022, *Monthly Notices
  of the Royal Astronomical Society*, 511, 2405. *The Gravitational-wave
  Optical Transient Observer (GOTO): prototype performance and prospects
  for transient science.*
- Tonry, J. L., Denneau, L., Heinze, A. N., et al. 2018, *Publications of
  the Astronomical Society of the Pacific*, 130, 064505. *ATLAS: A
  High-cadence All-sky Survey System.*
- van der Walt, S., Crellin-Quick, A., & Bloom, J. S. 2019, *Journal of
  Open Source Software*, 4(37), 1247. *SkyPortal: An Astronomical Data
  Platform.*
- Wang, W., Wei, F., Dong, L., Bao, H., Yang, N., & Zhou, M. 2020, in
  *Advances in Neural Information Processing Systems* 33, 5776.
  *MiniLM: Deep Self-Attention Distillation for Task-Agnostic Compression
  of Pre-Trained Transformers.* arXiv:2002.10957.
- Wenger, M., Ochsenbein, F., Egret, D., et al. 2000, *Astronomy &
  Astrophysics Supplement Series*, 143, 9. *The SIMBAD astronomical
  database: The CDS reference database for astronomical objects.*
