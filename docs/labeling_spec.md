# Labeling Spec — `data/labels/hand_v1/`

**Status:** v1 draft. Iterate as labeling surfaces ambiguities. Every iteration bumps
this doc AND the directory name (`hand_v2/`...) — labels never silently migrate.

**Audience:** the human labeler(s) who produce the ground-truth `CircularExtraction`
JSON files. The point isn't to extract everything — it's to surface schema gaps and
disagreements *before* scaling to 50 and *before* writing the LLM prompt.

---

## Workflow

For each circular `<id>` in `data/labels/hand_v1/`:

1. Read `<id>.source.md` (subject + body + provenance).
2. Edit `<id>.label.json` in place, filling fields the circular explicitly states.
3. **Use `null` when a field is not stated.** Never guess, never extrapolate from
   another source, never fill in a "common-sense" default.
4. Validate: `circex label validate data/labels/hand_v1/` (added in Sprint 1).
5. If the schema can't represent something the circular says clearly, **open an
   issue in this doc** under "Known gaps" — don't shoehorn into a wrong field.

---

## Field-by-field rules

### `circular_id`
Always set to the integer ID from the source filename. Already pre-filled in the
template; do not change.

### `event`
- `event_name`: As written, including "GRB " prefix (`"GRB 990123"`). If multiple
  names refer to the same event (e.g., GW170817 / AT2017gfo / SSS 17a), use a list.
- `id`: Mission-specific trigger ID if mentioned (e.g., `"bn230313485"`,
  `"1159327"`). Not the circular ID.
- `data_archive_page`: URL only if explicitly given as a data archive link.

### `follow_up`
Use ONLY when the circular is following up a *different* event (most commonly:
GW or neutrino → optical). Self-reports do not populate this field.

- `ref_type`: `"GW"`, `"neutrino"`, `"GRB"`, etc. As the circular labels the
  parent event.
- `ref_instrument`: `"LVK"`, `"IceCube"`, `"Fermi-GBM"`, etc.
- `ref_ID`: The trigger ID of the parent event, exactly as written.
- `reference`: Map of cross-references. Cite as `{"gcn_circular": 12345}` or
  `{"gcn_notice": "LVK-S190425z-1-Preliminary"}`. Multiple refs as multiple keys.

### `localization`
- `ra`, `dec`: ALWAYS decimal degrees, ICRS J2000. If the circular gives
  sexagesimal, convert (the LLM and regex extractors will too — this is the
  storage format). Use `astropy.coordinates.SkyCoord` if unsure.
- `ra_dec_error`: float for a circular error region [deg]. Array of 1–3 numbers
  for an ellipse: [semi-major, semi-minor, position-angle] in degrees.
- `containment_probability`: only set if explicitly stated. (Default of 0.9 is
  the *consumer's* responsibility, not the labeler's.)
- `systematic_included`: only set if the circular explicitly says so.

### `datetime` (note the alias — JSON key is `datetime`, Python attr is `datetime_`)
- All times in ISO 8601 with timezone offset (use `Z` for UTC). Convert if the
  circular gives MJD or year-fractional notation.
- `trigger_time` is the absolute trigger time of the event being reported on.
  If the circular reports an observation of an event whose trigger time is
  elsewhere, leave this null (or set in `follow_up.reference`).
- `observation_start`, `observation_stop`: when the actual photometry was
  taken. Not the time of the circular submission.
- `observation_livetime`: total integration / exposure time [seconds]. Sum
  rows if the body has a table.

### `time_offsets`
Each literal "T+234 sec" or "T+8.3 hours" mention becomes one entry. Do NOT
convert to absolute time — the whole point of this field is to preserve the
circular's literal phrasing.
- `value`: numeric coefficient
- `unit`: one of `s`, `m`, `h`, `d`
- `reference`: whatever the circular labels the offset relative to. Common
  values: `"T+"`, `"T-"`, `"trigger"`, `"GW alert"`, `"BAT trigger"`.

If a circular says "observations began approximately 4 hours after the trigger,"
that's `{value: 4, unit: "h", reference: "trigger"}`. If it says "T+234 s",
that's `{value: 234, unit: "s", reference: "T+"}`.

### `photometry` (list)
**One row per (filter, epoch).** A multi-epoch table with N epochs and M filters
produces N×M rows (one for each non-empty cell).

- `filter`: instrument-specific name as written (`g`, `r`, `R`, `clear`,
  `B`, `V`, `J`, `K`, `Ks`, etc.). Don't normalize Sloan vs Bessel — the
  source identifies the system.
- `mag`: apparent magnitude. Null for upper limits (use `limiting_mag` instead).
- `mag_error`: 1-sigma uncertainty. Null if not reported.
- `mag_system`: one of `"AB"`, `"Vega"`, `"STMag"`. **Inference rules:**
  - Sloan/PS1/SDSS filters (`u, g, r, i, z, y`) default to AB unless circular
    says otherwise.
  - Bessel filters (`U, B, V, R, I`) default to Vega unless circular says AB.
  - 2MASS `J, H, K, Ks` are Vega.
  - If genuinely unstated and not inferable, leave null (don't guess).
- `limiting_mag`: upper limit in same units. Mutually exclusive with `mag` —
  if `mag` is set, `limiting_mag` is null and vice versa.
- `limiting_mag_sigma`: sigma level of the upper limit (3, 5, etc.).
- `telescope`: facility name as written (`"Pan-STARRS1"`, `"ZTF"`, `"GTC"`,
  `"NOT"`, `"Keck"`, `"Subaru"`). Distinct from `reporter.mission`.
- `instrument`: camera/spectrograph name (`"OSIRIS"`, `"ALFOSC"`,
  `"ZTF Camera"`).
- `calibration_reference`: one of `PS1`, `SDSS`, `APASS`, `2MASS`, `Gaia`,
  `Other`. Use `Other` for cited catalogs that don't match (with a comment in
  the labeling notes).
- `galactic_extinction_corrected`: true ONLY if circular explicitly says
  "corrected for Galactic extinction" or equivalent.
- `seeing`: seeing FWHM in arcsec, when stated.
- `airmass`: airmass when stated.

### `spectroscopy`
List of `SpectralLine` entries. Only populate when the circular reports
identified lines. Each entry:
- `line_id`: short label (`"Halpha"`, `"OIII 5007"`, `"MgII 2796/2803"`).
- `rest_wavelength`: Angstroms.
- `observed_wavelength`: Angstroms.
- `equivalent_width`: Angstroms. Positive = emission, negative = absorption.
  Use null if EW not reported.

### `classification`
- `classification`: must be a canonical class name from
  skyportal/timedomain-taxonomy. The validator will reject otherwise. Use
  `circex.taxonomy.normalize_classification(text)` if you need to map an
  alias (e.g., `"SNIa"` → `"Ia"`).
- `subtype`: free-form refinement when the taxonomy is too coarse
  (`"Ia-CSM at +12d"`).
- `confidence`: float in [0, 1] only if circular reports a probability or
  qualitative confidence (`"highly likely" ≈ 0.9`).

### `redshift`
- `redshift`: numeric z.
- `redshift_error`: float for symmetric, [lower, upper] for asymmetric.
- `redshift_measure`: `"spectroscopic"` (from spectral features) or
  `"photometric"` (from broad-band SED).
- `redshift_type`: `"emission"`, `"absorption"`, or `"host"`. If both emission
  and absorption lines were used, prefer whichever the circular emphasizes;
  open an issue if genuinely ambiguous.

**Bound redshifts** (e.g. "z ≤ 1.61", "z ≥ 0.2", "z =< 1.61" in older
circulars): set `redshift: null` and append the literal phrase to
`extraction_meta.notes` as `"redshift_bound: <phrase>"`. The regex
extractor already populates this convention via `parse_redshift_bound`;
the LLM extractors should follow the same rule (LLM prompt: when the
text states only an inequality on z, leave redshift null and add the
phrase to notes). A `_redshift_bound` provenance key points at the source
phrase so downstream consumers can render it as a comment rather than a
structured value. The schema-level fix (a `redshift_bound: Literal["upper",
"lower","point"]` enum) is deferred to a v2 upstream PR.

### `reporter`
The *alerting party*, not the photometry instrument. For optical observation
circulars, this is usually the optical observing team's mission/instrument.

- `mission`, `instrument`: as written.
- `record_number`: only if the circular explicitly numbers itself (`"Notice
  #3"`).
- `messenger`: `"EM"` for optical; `"GW"` only for the parent GW event when
  that's what's being reported; `"Neutrino"` analogously.
- `spectral_band`: 2-element list [low, high] in `spectral_band_units`.
- `spectral_band_units`: `"keV"`, `"nm"`, or `"MHz"`. Optical = nm.

### `extraction_meta`
Always set to:
```json
{ "extractor": "hand-v1", "model_id": null, "prompt_version": null,
  "tokens_in": null, "tokens_out": null, "latency_ms": null,
  "cost_usd": null, "cache_hit": false }
```
Already pre-filled in the template.

---

## Adjudication log

Each labeling session, append decisions you made that aren't fully captured by
the rules above:

```
2026-MM-DD circular 216: z ≤ 1.61 stored as redshift=1.61.
           Open question: schema for lower/upper bounds?
```

Keep this section short. If a pattern recurs, lift it into the field rules
above and bump to `hand_v2/`.

---

## Known gaps

(Append as discovered. Items here become Sprint-1-end schema-revision proposals.)

- (placeholder; fill in during labeling)

---

## Sanity checklist before declaring a label "done"

- [ ] `circex label validate <file>` passes (schema OK, taxonomy OK).
- [ ] Every populated field has direct textual support in the source.
- [ ] No defaults populated where the source is silent (use `null`).
- [ ] Multi-row tables expanded to one `photometry[]` row per (filter, epoch).
- [ ] Redshift method, type, and error captured if z is given.
- [ ] Classification (if any) matches a canonical taxonomy class.
- [ ] Coordinates are decimal degrees, ICRS J2000.
- [ ] `extraction_meta.extractor == "hand-v1"`.
