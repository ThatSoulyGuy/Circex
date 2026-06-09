# Real-world test — the GRB 260604C flurry

**Date run:** 2026-06-08. **Extractor:** regex baseline (`regex-v1`). **Source:**
live `https://gcn.nasa.gov/circulars/{id}.json` fetches.

A "flurry" — many circulars about one event over a few days — is the hardest and
most representative test of the pipeline, because it exercises the multi-circular
machinery (event-name resolution, the cross-reference graph, `find_counterparts`,
cone search) on top of per-circular extraction. GRB 260604C drew a 20-circular
flurry from ~14 telescopes (Fermi, SVOM, GECAM-B, MASTER, LAST, Jinshan,
COLIBRÍ, Kilonova-Catcher, GOTO, Liverpool, GRANDMA, Mondy, SAO RAS, …).

The seed circular is saved at
[`fixtures/grb260604c_44877.json`](fixtures/grb260604c_44877.json) (#44877, SAO
RAS). The other 19 are reachable from its `follow_up` cross-references.

## How to reproduce

```python
import json, time, urllib.request
from circex.extract.protocol import Circular
from circex.extract.regex import RegexExtractor

def fetch(cid):
    req = urllib.request.Request(
        f"https://gcn.nasa.gov/circulars/{cid}.json",
        headers={"User-Agent": "circex/0.1"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

seed = json.load(open("docs/fixtures/grb260604c_44877.json"))
ext = RegexExtractor()
seed_ex = ext.extract(Circular.from_record(seed))

# The flurry is the seed plus its cross-referenced circulars:
xrefs = [int(x) for x in
         seed_ex.follow_up.reference["gcn_circulars"].split(",")]
for cid in xrefs:           # traverse the flurry
    ext.extract(Circular.from_record(fetch(cid)))
    time.sleep(0.15)        # be polite to the server
```

(Set `CIRCEX_TAXONOMY_DIR=references/timedomain-taxonomy/tdtax` so the
classification matcher loads.)

## Results

20/20 circulars fetched and extracted live.

### Final output (regex baseline, after the classification fixes)

```
  circ  event        class      phot xref  subject
----------------------------------------------------------------------------------------------------
 44877  GRB 260604C  GRB           1   19  GRB 260604C: further SAO RAS optical observations
 44822  GRB 260604C  long GRB      0    0  GRB 260604C: Fermi GBM Final Real-time Localization
 44831  GRB 260604C  GRB           0    3  GRB 260604C: Fermi GBM Observation
 44823  GRB 260604C  GRB           0    1  GRB 260604C: SVOM detection of a long burst
 44854  GRB 260604C  GRB           0    3  GRB 260604C: GECAM-B observation
 44827  GRB 260604C  None          0    0  GRB 260604C: MASTER OT J145749.59+284903.0 optical ...
 44828  GRB 260604C  GRB           0    3  GRB 260604C: LAST detection of optical counterpart ...
 44836  GRB 260604C  GRB           0    1  GRB 260604C: Correction to GCN 44828
 44832  GRB 260604C  None          1    4  GRB 260604C: Jinshan optical observations
 44834  GRB 260604C  GRB           8    5  GRB 260604C: SVOM/COLIBRÍ (FM-GFT) optical observations
 44835  GRB 260604C  GRB           0    8  GRB 260604C: Kilonova-Catcher optical afterglow detection
 44837  GRB 260604C  GRB           0    7  GRB 260604C: GOTO detections of the optical afterglow
 44843  GRB 260604C  GRB           1    7  GRB 260604C: Liverpool Telescope optical detection
 44851  GRB 260604C  GRB           0    7  GRB 260604C: GRANDMA observations
 44852  GRB 260604C  GRB           1   12  GRB 260604C: SAO RAS optical observations
 44857  GRB 260604C  GRB           0    4  GRB 260604C: OPD1.6m - GRANDMA observations - detection
 44858  GRB 260604C  GRB           0   12  GRB 260604C: Simeiz Zeiss-1000 optical observations
 44862  GRB 260604C  GRB           0   13  GRB 260604C: Mondy optical observations: evidence of ...
 44865  GRB 260604C  GRB           0    4  GRB 260604C: GRANDMA further observations
 44873  GRB 260604C  GRB           0    4  GRB 260604C: SVOM/COLIBRÍ (FM-GFT) colour evolution
----------------------------------------------------------------------------------------------------
distinct events:        ['GRB 260604C']        (consistent across all 20)
classification hits:    18/20  — 0 garbage; all 'GRB'/'long GRB' or None
photometry rows (regex): 12   (was 10; the spaced-detection recognizer recovered
                                the SAO RAS detections in #44877 and #44852)
cross-reference union:   22 circulars
```

`class` is now clean: every value is the tautological-but-correct `GRB`/`long
GRB` or `None` — the 9 garbage classifications from the pre-fix run (`Overtone`,
`Mira`, `Orion`, `FU Ori`, and the `kilonova` telescope-name match) are gone.
`phot` shows the regex baseline's recall on photometry (12 rows total; the
spaced-detection recognizer recovers the SAO RAS detections, but multi-row
tables remain the LLM extractor's job — see below).
`xref` is the per-circular cross-reference count; their union (22) is the event
graph the multi-circular machinery reconstructs from any seed.

### What worked — the structural spine

- **Flurry reconstruction.** From the one seed, `follow_up` extracted **19**
  cross-references; traversing them pulled the whole event, and the reference
  union expands to **22** (more reachable). All 20 circulars resolved to one
  consistent event name, `GRB 260604C`. This is the spine of multi-circular
  event handling and the basis for `find_counterparts`.
- **New per-row fields populate where photometry is caught.** #44834's grizy
  table extracted with canonical bandpasses (`r→sdssr`, `g→sdssg`, `i→sdssi`,
  `z→sdssz`, `y→ps1::y`), `is_detection=True`, and AB/Vega inference. #44843:
  `r = 18.6 ± 0.05 → sdssr`.
- **Provenance makes wrong answers visibly wrong** (see classification below).

### What failed — exactly where the design predicts

**1. Classification false positives — a real, fixable bug.** ~9 of 12
classification hits across the flurry are garbage from single-letter / substring
alias matches:

| Circular | Bogus class | Matched snippet | Actual source |
|---|---|---|---|
| #44877 | `Overtone` | `"O"` | author initial *O. Spiridonova* |
| #44834 | `FU Ori` | `"Fu"` | a word fragment |
| #44834, #44835 | `Mira` | `"M"` | author initial |
| #44854, #44827 | `Orion` | `"in"` | substring |
| #44828, #44836, #44837 | `Overtone` | `"O"` | author initial |

Provenance saves the *consumer* — every bogus snippet (`"O"`, `"M"`, `"in"`,
`"Fu"`) is trivially filterable — but the matcher itself needs a guard:
**minimum alias length + a classification-context keyword requirement** before
accepting short aliases.

> **Update (fixed):** two guards landed. (1) `classification.py` drops 1-char
> aliases and gates 2-char aliases on a classification-context cue. (2) It also
> rejects an alias heading a hyphenated proper noun (`"Kilonova"` inside the
> *Kilonova-Catcher* telescope name) while keeping `kilonova-like`, `II-P`,
> `Ia-CSM`. Re-running this flurry, the classification distribution collapses to
> `GRB`×17 / `long GRB`×1 / `None`×2 — **zero garbage** (all of `Overtone`,
> `Mira`, `Orion`, `FU Ori`, and the `kilonova` telescope-name match are gone).
> The only remaining output is the tautological-but-correct `"GRB"`. See
> [`known_issues.md`](known_issues.md).

**2. Photometry recall is poor and lossy — the documented "irregular table"
failure.**

- **The seed's own detection was originally missed.** #44877 states
  `Rc 23.08 +/- 0.18, UL 23.8` at `t-T0 = 4.011 d`, and the multi-row table
  parser returned **0 rows**: the table has a two-line header, `Mag +/- Err`
  split across columns, and a dotted date `2026.06.08` — exactly the layout the
  multi-row parser skips conservatively.
- Even the other hits are partial: `mag_error`/`limiting_mag` are mostly
  dropped, and #44832's `R = 16.1` is suspect (too bright for a 4-day
  afterglow — likely a calibration-star or coordinate misparse).

> **Update (partly fixed):** a surgical, high-precision recognizer for the
> space-separated `<filter> <mag> ± <err>` measurement line (mandatory `±`, with
> Cousins/primed filters like `Rc`) now recovers the seed's detection —
> `R = 23.08 ± 0.18`, `bessellr`, Vega, `is_detection=True` — taking the flurry
> from 10 to 12 photometry rows. This deliberately does **not** parse multi-row
> tables (the documented regex/LLM eval boundary stays); it only catches the
> single-detection line the column-split parser drops. The trailing `UL 23.8`
> and the `t-T0` epoch are still not captured (see #3) — multi-column structure
> is still the LLM extractor's job.

**3. obs_mjd unresolved here.** No `trigger_time` was supplied, and the seed's
`t-T0 = 4.011 d` relative epoch wasn't captured because its photometry row was
missed. Passing `trigger_time` to `extract_text` would resolve relative epochs
*if* the table parsed.

**4. Telescopes.** Zeiss-1000, MASTER, LAST, COLIBRÍ, GOTO, Liverpool, GRANDMA,
Mondy are not in the seed alias map, so `telescope_canonical` is null
(passthrough, as designed). This is what ICARE's `instrument_id` table fills.

## Takeaway

The flurry is the project thesis in miniature: the regex baseline nails the
**structural backbone** (event ID + the 19-way cross-reference graph) and fails
exactly where the writeup predicts — **irregular photometry tables and in-prose
classification** — except the failures are now *auditable via provenance*
instead of silent. It is a textbook case for the Claude/Ollama extractors
(wired; needs an API key / Ollama daemon to run).

## Action items surfaced by this test

1. **Fix the classification short-alias false positives** (min-length + context
   guard). Severe enough here that single letters match author initials.
2. **Improve multi-line-header / split-`Mag ± Err` table parsing**, or accept it
   as the LLM-extractor boundary (consistent with the eval design).
3. **Consider this flurry a regression fixture** — the seed is saved; the
   cross-ref traversal reconstructs the rest.
