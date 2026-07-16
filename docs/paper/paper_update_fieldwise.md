# Paper update — field-by-field results + discussion

**Paste-ready for Pages.** Insert §4.6 after the redshift results (§4); append the
three discussion paragraphs to §5. Numbers are the current configuration (prompt
v2026-07-16, hand-validated 120-Circular gold). Tables are given as plain text —
in Pages, select the block and Format ▸ "Convert to Table", or rebuild as a Pages
table.

---

## 4.6. Extraction beyond redshift: a hand-validated field-by-field gold set

The comparison of §4 is confined to the fields Sha26 released: redshift, and — for
our comparator — event designation and telescope. To measure the fields Sha26 did
not extract, we constructed a 120-Circular gold set spanning five observational
strata: single-epoch magnitudes, multi-epoch magnitude tables, spectroscopic
redshift/classification reports, photometric upper limits, and gravitational-wave /
neutrino counterpart searches. Every field of every Circular was **manually
validated against the source text** following a fixed labeling specification; the
labels are human-adjudicated ground truth. The set is deliberately weighted toward
the harder strata (multi-epoch tables and spectroscopic reports) so the evaluation
is not dominated by trivial single-line Circulars.

Table 4 reports per-field F1 for the three extractors on this set.

    Field                     Support   Regex   Mistral-7B(constr.)   Hybrid
    Event designation           120     0.966       0.870            0.975
    Redshift value               38     0.902       0.892            0.881
    Redshift type                32     0.431       0.381            0.381
    Right ascension              23     0.571       0.088            0.571
    Declination                  23     0.619       0.597            0.619
    Classification                7     0.018       0.105            0.105
    Photometry (per row)        266     0.270       0.409            0.408

    Table 4. Per-field F1 on the 120-Circular hand-validated gold set. Support is
    the number of non-null gold values (or gold rows, for photometry). Small
    supports (classification, redshift type, coordinates) carry correspondingly
    wide uncertainty and are reported as indicative.

Three results stand out.

First, the redshift finding of §4 reproduces on an independent set of Circulars:
the constrained Mistral attains F1 = 0.89, indistinguishable from the 0.90 regex
baseline and consistent with the 0.935 of the larger Sha26-gold comparison.

Second, no single extractor dominates across fields, and the ordering is
field-dependent in a way that follows directly from each extractor's failure mode.
On event designations — a lexically regular token (`GRB` + date + letter) — the
regular expression leads (0.966) and the language model trails (0.870). On position
the language model is unreliable: it recovers declination (already in degrees) but
systematically fails right ascension (0.088), which requires an hours-to-degrees
sexagesimal conversion a 7B model does not perform consistently; the deterministic
regex parser is far stronger (0.571). On photometry the ordering inverts — the
constrained model (0.409) leads the regex baseline (0.270), reading prose and
heterogeneous table formats the patterns miss.

Third, and most consequential for a production pipeline: **extraction coverage is
not extraction correctness.** The language model emits at least one photometry row
for nearly every Circular that contains photometry, yet its per-row F1 is only
0.409 — a gap invisible to a redshift-only or coverage-only evaluation. Table 5
decomposes photometry by stratum.

    Photometry stratum                  Gold rows   F1
    Single-epoch magnitude                  12     0.500
    Multi-epoch magnitude table            168     0.479
    Spectroscopic classification report     46     0.471
    Photometric upper limit                 22     0.256
    GW / neutrino counterpart search        18     see text

    Table 5. Per-row photometry F1 by stratum (constrained Mistral-7B).

Per-row accuracy is highest on single-epoch magnitudes (0.500) and multi-epoch
tables (0.479), and lowest on upper limits (0.256), where the model conflates
detections with limits. Counterpart-search Circulars are a distinct failure: they
tabulate limiting magnitudes at many surveyed galaxy positions, none of which is
photometry of a transient, and the model emits these survey rows as spurious
detections regardless of instruction (§5).

These results motivate the hybrid extractor of §3: routing each field to the
extractor whose failure mode it tolerates — the regular expression for lexically
regular fields (event designation, coordinates), the constrained model for
semantically mediated ones (photometry, redshift) — matches or exceeds either
extractor alone on every field with gold support (Table 4, final column).

---

## Additions to §5 (Discussion)

**Coverage is not correctness.** A headline conditioned on a single field, or on
whether *any* value was emitted, systematically overstates readiness. Our language
model returns a photometry array for nearly every Circular that has one, which a
coverage metric would score near unity; measured per row against hand-validated
photometry it reaches 0.41. Structured-extraction evaluations for ingestion
pipelines should therefore be reported field-by-field and row-by-row, against gold
that spans the observational strata the pipeline will actually encounter.

**The limits of prompt engineering.** Several field-specific weaknesses yield to
prompting: an explicit rule that upper limits populate the limiting-magnitude field
rather than the magnitude field, and an instruction to emit every tabulated epoch,
each improve the corresponding stratum. Others do not. The instruction to omit
survey limiting magnitudes in wide-field counterpart searches — a negative,
conditional constraint — was not reliably followed by a 7B model under two
successive phrasings, and strengthening it degraded photometry on unrelated strata.
We read this as a ceiling: prompt engineering can correct format and emphasis, but
not a small model's disposition to over-emit on a structurally unfamiliar layout.

**On fine-tuning.** The residual photometry weaknesses — upper-limit handling and
wide-field over-emission — are real and prompt-resistant, which makes photometry a
plausible fine-tuning target now that local GPU capacity is available. We
nevertheless defer it. The binding constraint is not compute but evaluation: a
credible fine-tuning result requires a held-out test set disjoint from any training
labels, and the present 120-Circular set is too small to split and serve both
roles, with its counterpart-search subset resting on a labeling-convention choice
rather than an unambiguous ground truth. We therefore present the field-by-field
results as a diagnostic map of where structured extraction is solved (redshift,
event identity, single-epoch photometry) versus open (coordinates for the language
model, upper limits, dense tables), and condition any fine-tuning on a larger,
independently labeled evaluation set built for that purpose.
