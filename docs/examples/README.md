# Example `CircularExtraction` output

Sample JSON produced by Circex extractors — the structured form of a GCN optical
circular. Every extractor (regex / Claude / Ollama) emits this same shape
(`circex.schema.CircularExtraction`), validated against `nasa-gcn/gcn-schema`.

| File | Input | Extractor | Shows |
|---|---|---|---|
| [`complete.regex.json`](complete.regex.json) | a clean synthetic circular | regex | the **full populated schema** — event, localization (RA/Dec), dated photometry (`obs_mjd`, `bandpass`, `is_detection`, `mag_error`, `mag_system`), classification + `taxonomy_path`, redshift, `provenance`, `follow_up` |
| [`grb260604c_44877.regex.json`](grb260604c_44877.regex.json) | a real circular ([#44877](https://gcn.nasa.gov/circulars/44877)) | regex | real-world output: the event, the 19-circular cross-reference graph (`follow_up`), one recovered detection, and `provenance` spans |
| [`grb260604c_44877.ollama.json`](grb260604c_44877.ollama.json) | the same real circular | Ollama / Mistral-7B | the LLM reads the table date → a **timed** photometry point (`obs_mjd`), which regex can't bind from that table layout |
| [`grb260604c_44877.annotated.json`](grb260604c_44877.annotated.json) | the same real circular | regex | the **value↔snippet** view for human validation — every field paired with the source snippet it came from |

## Snippet-paired output (for validation UIs)

`circex annotate` flattens an extraction into a per-field map where each value
is paired with the source-text **snippet** (and char offsets) it came from —
made for snippet-level human validation:

```json
{
  "event.event_name":   { "value": "AT2026xyz", "snippet": "AT2026xyz", "start": 0, "end": 9 },
  "localization.ra":    { "value": "224.512", "snippet": "RA = 224.512, Dec = +28.804", "start": 98, "end": 125 },
  "redshift.redshift":  { "value": "0.512", "snippet": "z = 0.512", "start": 315, "end": 324 },
  "photometry[0].mag":  { "value": "20.42", "snippet": "2026-06-10  r  20.42  0.05", "start": 207, "end": 243 }
}
```

`snippet` is `null` when the extractor recorded no span for a field. A consumer
that wants only the value reads `.value`; a validation UI shows `.snippet`.

```bash
circex annotate --from-file <circular.json> --extractor regex         # one, to stdout
circex annotate --circulars-dir circulars/ --extractor ollama --out extracted/   # batch -> extracted/<id>.json
```

## Field tour (see `complete.regex.json`)

```jsonc
{
  "circular_id": 99001,
  "event":          { "event_name": "AT2026xyz" },
  "localization":   { "ra": 224.512, "dec": 28.804 },          // ICRS J2000 deg
  "photometry": [
    { "filter": "r", "bandpass": "sdssr", "mag": 20.42, "mag_error": 0.05,
      "mag_system": "AB", "is_detection": true, "obs_mjd": 61201.0 }
  ],
  "classification": { "classification": "Ia",
      "taxonomy_path": ["Time-domain Source","Stellar variable",
                        "Cataclysmic","Supernova","Type I","Ia"] },
  "redshift":       { "redshift": 0.512, "redshift_type": "host" },
  "follow_up":      { "reference": { "gcn_circulars": "12345" } },
  "provenance": {                                              // (start,end,snippet) per value
    "redshift": { "start": 315, "end": 324, "snippet": "z = 0.512" }
  },
  "extraction_meta": { "extractor": "regex-v1", ... }
}
```

Key extracted parameters: `bandpass` is the sncosmo/SkyPortal filter name;
`obs_mjd`/`obs_time` is the per-point epoch (UTC); `is_detection` distinguishes a
measurement from an upper limit; `provenance` maps each value back to the
`(start, end, snippet)` it came from in the source text.

> Note: the Ollama sample shows the raw LLM output, which can mislabel a band
> (here Cousins `Rc` → `sdssr`); the SkyPortal poster applies a deterministic
> filter crosswalk that corrects this to `bessellr`/`vega` before posting.

## Regenerate / make your own

```bash
# JSON for one circular, any extractor, straight to stdout via the poster path:
circex post --from-file <circular.json> --extractor regex      # or ollama / claude-haiku

# or batch-extract to files:
circex extract --extractor regex --circulars data/labels/hand_v1 --out runs/regex
```

The JSON Schemas these conform to are in [`../../schemas/`](../../schemas)
(`Photometry.schema.json`, `Classification.schema.json`,
`SpectralLines.schema.json`), versioned via `schemas/VERSION`.
