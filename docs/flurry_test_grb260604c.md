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
accepting short aliases. This is the documented "regex fails on in-prose
classification" weakness, now quantified into an actionable fix. See
[`known_issues.md`](known_issues.md).

**2. Photometry recall is poor and lossy — the documented "irregular table"
failure.**

- **The seed's own detection was missed.** #44877 states
  `Rc = 23.08 ± 0.18, UL 23.8` at `t-T0 = 4.011 d`, but the regex table parser
  returned **0 rows**: the table has a two-line header, `Mag +/- Err` split
  across columns, and a dotted date `2026.06.08` — exactly the layout the parser
  is built to skip conservatively.
- Even the hits are partial: `mag_error`/`limiting_mag` are mostly dropped, and
  #44832's `R = 16.1` is suspect (too bright for a 4-day afterglow — likely a
  calibration-star or coordinate misparse).

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
