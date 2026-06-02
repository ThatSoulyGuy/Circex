# Prompt Deltas vs Vidushi/Sharma 2026

Reference: `references/circulars-nlp-paper/information-extraction/redshift_extraction.ipynb`
and `references/circulars-nlp-paper/figures/Fig6_sample_prompt.pdf`.

This doc records what Circex's `PROMPT_V1` does differently from her published
Mistral-7B prompt, and why. Each item is a deliberate departure — if a labeler
or paper reviewer asks "why didn't you copy her prompt exactly," the answer is
here.

---

## What stayed the same
- Single zero/few-shot prompt; no chain-of-thought scaffolding.
- Source text appears as `<circular>...</circular>` style delimiters (so the
  model isn't confused by inline tags inside the body).
- Explicit "use null when not stated" instruction.

## What changed

### 1. Scope expanded from 4 fields → ~20 fields
**She extracts:** redshift, GRB number, telescope name, redshift type.
**We extract:** the full `CircularExtraction` schema — identifiers, astrometry,
times, full photometry tables, spectroscopy lines, classification, GCN
cross-refs, etc.
**Why:** the project goal is structured extraction over the whole optical
schema, not just redshift. Her 4 fields remain the apples-to-apples baseline
for the eval table.

### 2. Tool-use enforces JSON schema vs prompt-and-pray
**She:** asks for JSON in the prompt, then regex-extracts a `{...}` block from
free-text response.
**We:** for Claude, define a `submit_extraction` tool whose `input_schema` is
the JSON Schema of `CircularExtraction` (minus `extraction_meta`); force tool
use; parse `tool_use.input` directly with Pydantic.
**Why:** eliminates the "model emits prose around JSON" failure mode. For
Ollama (no first-class tool use), we use JSON-mode + one repair retry with the
validation error appended.

### 3. Magnitude system inference rules baked in
**She:** doesn't specify.
**We:** explicit rules in the system text: Sloan→AB, Bessel→Vega, NIR→Vega,
leave null when genuinely unstated and not inferable.
**Why:** the new `mag_system` field is a Literal enum [AB, Vega, STMag];
without inference rules the model would either guess wrong or always null.

### 4. T+offset stored literally, not resolved
**She:** doesn't extract time offsets at all.
**We:** explicit instruction to capture `T+234s` style phrasings as
`{value, unit, reference}` LITERALLY, not resolved against the absolute trigger
time T0 (PDF decision 4).
**Why:** consumers (including SkyPortal) often want the literal phrasing back;
T0 resolution is a separate inference step we don't want bundled into extraction.

### 5. Classification → canonical taxonomy alias resolution
**She:** doesn't extract classification.
**We:** the model must emit a canonical class name from skyportal/timedomain-
taxonomy (175 classes). The system text instructs alias→canonical mapping
client-side ("SNIa" → "Ia").
**Why:** the new `Classification` schema validates against the canonical set.
The model gets a clear contract; the regex baseline does the same lookup.

### 6. Few-shot examples cover 4 of 5 strata; 1 stratum held out
**She:** zero-shot for redshift extraction.
**We:** 4 few-shots covering multi-row mag table, in-prose classification,
upper limit, GCN cross-ref. The fifth stratum (GW/neutrino counterpart) is
deliberately UNSEEN in the prompt so the eval measures generalization, not
few-shot memorization.
**Why:** without few-shots, format errors (esp. mag tables) dominated early
prototype runs.

### 7. Span-level provenance grounding (PROMPT_V1 = `2026-05-30`)
**She:** no source-text grounding; each extracted value is unanchored.
**We:** the system prompt now requires every populated field to also appear
in a `provenance: dict[str, Span]` map keyed by dotted field path
(`"redshift"`, `"photometry[0]"`) or — preferred — leaf field path
(`"redshift.redshift"`, `"photometry[0].mag"`). Each `Span` is
`{start, end, snippet}` with `snippet == body[start:end]` so a downstream
consumer can round-trip-verify the offsets. Few-shot #2 (AT2024xyz / Ic-BL /
z = 0.215) demonstrates the leaf-level pattern with four verified spans
(`event` → "AT2024xyz", `classification` → "Ic-BL", `redshift.redshift` →
"z = 0.215", `redshift.redshift_error` → "0.001").

The prompt also instructs the model to omit entries it cannot localize to
a single contiguous range (e.g., a value inferred from a disjoint
combination of phrases), rather than guess offsets.

**Why:** grounding turns the extractor from "trust the JSON" into "show
your work." Downstream operators (SkyPortal, eval graders, the hand-label
audit pass) can verify any claim without re-reading the prose, and a future
attribution-scoring extension to the eval becomes possible (does the cited
span actually justify the value, not just is the value correct).

**Cache impact:** bumping `PROMPT_V1` from `2026-05-13` to `2026-05-30`
invalidated the previous LLM cache entries cleanly. The provenance
instructions add ~300 tokens to the system text; for a 7B model like
Mistral this measurably increases prompt-eval latency on small machines
(see `docs/known_issues.md` for the observed p50/p95 on Apple Silicon).

---

## Eval implications

Two metrics matter at Sprint 4 close:
1. **On her 4 fields:** we MUST beat her published redshift/GRB#/telescope/
   redshift-type F1 numbers. This is the headline acceptance criterion. The
   prompt-design departures above are bets that schema-enforced extraction +
   few-shots win over her free-text JSON approach.
2. **On the other ~20 fields:** no baseline to beat; report regex vs Claude vs
   Ollama directly.

Any divergence > 10% from her published Mistral numbers on the 4 shared fields
gets a row in this doc explaining suspected causes (model size, quantization,
prompt difference, eval-set drift).
