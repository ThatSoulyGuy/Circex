# Design — SkyPortal poster bot ("icarebot")

**Status:** mapping + dry-run implemented; live HTTP posting gated on a target
instance + token + explicit sign-off. Tracks the ICARE integration.

## Goal

Turn a Circex `CircularExtraction` into SkyPortal API writes: upsert the source,
post photometry points, set the redshift, and attach provenance as comments.
This is the *push* direction (Circex → SkyPortal), complementary to the LeanMCP
bridge's *pull* direction (SkyPortal → Circex tools).

## Pipeline

```
gcn.circulars (Kafka)  ─►  extract_text  ─►  CircularExtraction
                                                   │
                                      skyportal_map.to_actions()
                                                   ▼
                                   SkyPortalActions {source, photometry[],
                                                     redshift?, comments[]}
                                                   │
                          ┌────────────────────────┴───────────────┐
                          ▼ (default)                              ▼ (--live + token)
                     dry-run: print payloads              POST to SkyPortal /api/*
```

For v1 the trigger is left open (manual circular / fixture replay, or a Kafka
consumer); the mapping and poster are trigger-agnostic.

## The mapping (CircularExtraction → SkyPortal)

| SkyPortal write | Source field | Notes |
|---|---|---|
| `POST /api/sources` `{id, ra, dec}` | `event.event_name` (normalized) → `id`; `localization.ra/dec` | id is the AT/GRB name with spaces removed. No source without a position **and** a name. |
| `POST /api/photometry` per row | `obs_mjd`→`mjd`, `bandpass`→`filter`, `mag`→`mag`, `mag_error`→`magerr`, `limiting_mag`→`limiting_mag`, `mag_system`→`magsys` (lowercased), `telescope_canonical`→`instrument_id` (via map) | A row **without `obs_mjd` cannot be posted** (SkyPortal requires a time) — those go to a comment, not silently dropped. `is_detection=False` ⇒ `mag/magerr=null`, `limiting_mag` set. `provenance` for the row → `altdata.note`. |
| `PATCH /api/sources/{id}` `{redshift, redshift_error}` | `redshift.redshift`, `redshift.redshift_error` | Only when a scalar redshift exists. **Bound redshifts** (`extraction_meta.notes` `redshift_bound:`) are **not** set here — they go to a comment (SkyPortal redshift is scalar). |
| `POST /api/sources/{id}/comment` `{text}` | `provenance`, `extraction_meta.notes`, untimed rows | Audit trail: each posted value's source span, bound redshifts, and any row we couldn't time. |

### Field conversions
- **`magsys`**: `AB`→`ab`, `Vega`→`vega`, `STMag`→`ab` (closest; flagged).
- **`filter`**: the `bandpass` field already holds the sncosmo name SkyPortal
  wants (`sdssr`, `bessellr`, `2massj`, …). A row without a `bandpass` is not
  postable as photometry (filter is required) → comment.
- **`instrument_id`**: `telescope_canonical` → SkyPortal numeric `instrument_id`
  via a caller-supplied map (ICARE's `instrument_id` table, e.g. `VT→114`,
  `COLIBRI-VIS→85`). Unmapped ⇒ `instrument_id=None` and a note; never guessed.

## Idempotency & safety

- **Dry-run is the default.** Live posting requires both `--live` and a token;
  the poster prints every payload first.
- Re-posting the same circular is safe at the Circex layer (the LLM cache and
  store key on `(circular_id, body_sha1, …)`); SkyPortal de-dups photometry by
  `(obj_id, instrument_id, mjd, filter)`, so re-delivered Kafka messages don't
  create duplicate points.
- Nothing is posted for an extraction with no source name **or** no position —
  a GRB circular reporting only photometry with no OT name/coords yields a
  comment-only action (or nothing), never a malformed source.

## Open decisions (gate going live)

1. **Target instance + token.** Which SkyPortal? A sandbox/preview first.
2. **Trigger.** GCN Kafka consumer now, or replay/manual for v1.
3. **Classification.** Circex's regex classification is weak/tautological on
   GRB circulars (see `flurry_test_grb260604c.md`); recommend **not** posting
   `classification` in v1 (or only from the LLM extractor with a confidence
   floor), to avoid polluting SkyPortal. Hold until the LLM column is run.
4. **Group/visibility.** Which SkyPortal `group_ids` the bot posts to.
