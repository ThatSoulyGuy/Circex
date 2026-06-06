# Design note — per-row photometry epoch (`obs_mjd`)

**Status:** IMPLEMENTED. Tracks ICARE P0 #2.
**Author:** Circex. **Date:** 2026-06-06.

**Decisions taken** (resolving §7): both `obs_mjd` (float MJD, UTC) and
`obs_time` (ISO-8601) are emitted; absolute-UT and relative resolution are both
implemented; caching follows §5(i) — the T0-independent absolute epochs are
cached, relative offsets are resolved per call from `Circular.trigger_time`.
The relative pairing uses the conservative single-epoch rule (§7.3). See
`circex/extract/timing.py` and the `PhotometryExt.obs_mjd/obs_time` fields.

## 1. Problem

SkyPortal photometry requires an observation time (`mjd`) on **every** point.
Circex's `PhotometryExt` currently has no per-row time field: timing lives at
the circular level (`DateTime.trigger_time`, `observation_start/stop`) and the
only per-measurement time signal — `time_offsets` — is captured **literally
and left unresolved** ("observations began T+234s") per the project plan's
decision 4. As a result icarebot falls back to a single circular-level time for
all rows and **skips rows it cannot time**, dropping real photometry.

The ask: resolve each row's epoch and emit `obs_mjd` (or an ISO timestamp) on
each `PhotometryExt`.

## 2. Where a row's time actually comes from

Three cases, in descending order of reliability:

1. **Absolute UT stated in the row.** Multi-row magnitude tables usually carry a
   `Date`/`MJD`/`Epoch` column (e.g. `2024-01-02 04:30`, or an MJD directly).
   This is the **common** case and needs no trigger time at all — parse it to
   MJD. The mag-table parser already *classifies* a `date` column
   (`_classify_columns` in `circex/extract/regex/mag_table.py`) but currently
   **discards the value**; wiring it through is most of the work.

2. **Relative offset (`T+234s`) plus a known T0.** Requires the trigger time.
   The circular almost never restates T0 — it assumes it. So T0 must come from
   outside the body (§3).

3. **Neither.** Prose like "we observed the field last night" — no resolvable
   epoch. `obs_mjd` stays `null` (and the row is still emitted, with whatever
   else was extracted).

## 3. Where does T0 come from?

`Circular.created_on` is the **submission** time of the circular (Unix ms),
often hours-to-days after the trigger — **not** a usable T0. Options:

- **(A) Caller-supplied.** Add `Circular.trigger_time: datetime | None`. For
  Kafka-delivered circulars the GCN broker already knows the trigger time of
  the associated event, so ICARE passes it in via `extract_text`
  (`{..., trigger_time}`). **Recommended primary source.**
- **(B) Lookup from a predecessor circular.** The event's discovery/trigger
  circular (FTS-indexed) often states T0. Possible later enhancement; adds a
  store dependency and cross-circular coupling. Out of scope for v1.
- **(C) None.** When no T0 is available, relative offsets cannot be resolved →
  `obs_mjd` is `null` for those rows. Never invent a T0.

## 4. Proposed schema change

Add to `PhotometryExt`:

```python
obs_mjd: float | None = Field(
    default=None,
    description=(
        "Observation epoch as Modified Julian Date (UTC). Resolved from an "
        "absolute UT stated in the row, else from the caller-supplied trigger "
        "time plus the row's relative offset. Null when neither is available."
    ),
)
```

Add to the `Circular` input dataclass (`circex/extract/protocol.py`):

```python
trigger_time: datetime | None = None  # T0 for resolving relative offsets
```

**`time_offsets` stays literal and unresolved** — decision 4 is *not* reversed.
`obs_mjd` is an additive, derived convenience field; the literal `TimeOffset`
records remain the audit-grade capture. A consumer that distrusts our
resolution can still read the raw phrasing. This is augmentation, not a policy
change.

## 5. Where resolution runs

**In the extractor**, not at serve/eval time. Rationale:

- The resolved `obs_mjd` is then cached alongside everything else under the LLM
  cache key `(extractor_id, model_id, prompt_version, circular_id, sha1(body))`
  and the query store — no re-computation per query.
- It keeps `search_by_position` / `get_photometry` results self-contained.

Caveat: the cache key does **not** include `trigger_time`. If the same body is
re-extracted with a *different* T0, the cache would return the stale `obs_mjd`.
Mitigations, pick one at implementation time:

- **(i)** Resolve absolute-UT rows in the extractor (cache-safe, T0-independent)
  but resolve relative-offset rows in a thin post-step that takes T0 — so the
  cached object carries `obs_mjd` for absolute rows and `time_offsets` for
  relative ones, and the relative→mjd step is applied per-call. Cleanest.
- **(ii)** Fold `trigger_time` into the cache key. Simple but lowers hit rate
  whenever T0 is refined.
- **(iii)** Document that T0 is immutable per circular in practice (true for
  GRBs once the trigger is published) and accept (i)'s simplicity without the
  post-step. Lowest effort, small correctness risk on T0 revisions.

Recommendation: **(i)** — absolute UT resolved-and-cached in the extractor;
relative offsets resolved on demand from the supplied T0.

## 6. Implementation sketch (when greenlit)

1. `PhotometryExt.obs_mjd` + `Circular.trigger_time` (schema + dataclass).
2. Mag-table parser: parse the already-classified `date` column with
   `astropy.time.Time` (accepts ISO and MJD), set `obs_mjd` per row. Provenance
   span points at the date token.
3. Single-mag prose parser: no date in the pattern today; leave `obs_mjd` null
   unless an absolute UT is adjacent (possible later).
4. Relative→absolute helper: `obs_mjd = Time(trigger_time).mjd + offset_seconds/86400`
   applied where a `TimeOffset` row pairs with a photometry row and T0 is known
   (per §5(i), at serve/extract boundary).
5. LLM prompt: instruct the model to set `obs_mjd` when the row states an
   absolute UT; leave null otherwise (do **not** have the LLM do T0 arithmetic).
6. `circex schema-dump` re-run + `SCHEMA_VERSION` **minor** bump (new optional
   field). Tests: absolute-UT table → mjd; MJD column passthrough; relative +
   T0 → mjd; no T0 → null; provenance on the date token.

## 7. Open questions for sign-off

1. **Field name/type:** `obs_mjd: float` (MJD, UTC) vs `obs_time: str` (ISO
   8601). MJD matches SkyPortal's photometry contract directly; ISO is more
   human-legible. **Recommend `obs_mjd`** (and ICARE converts trivially if it
   wants ISO).
2. **Caching strategy:** §5(i) vs (ii) vs (iii). **Recommend (i).**
3. **Scope of relative resolution:** only when a `TimeOffset` unambiguously
   pairs with a photometry row (1:1), or skip relative resolution entirely in
   v1 and ship only absolute-UT rows? Absolute-UT alone already unblocks the
   common multi-row-table case; relative pairing is fuzzier. **Recommend:
   ship absolute-UT resolution first; treat relative pairing as a fast-follow.**

## 8. Effort

- Absolute-UT path (covers most real photometry tables): ~half a day incl.
  tests and schema re-dump.
- Relative-offset pairing + T0 plumbing through `extract_text`: ~another half
  day, gated on the §7.2 / §7.3 decisions.
