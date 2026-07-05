# Live consumer — `circex consume`

Processes **every incoming GCN circular** into SkyPortal. This is the ICARE
production path: circulars stream in, and sources build themselves.

## Per-circular pipeline

For each circular (`circex/consume/processor.py::process_circular`):

1. **Reconstruct the event** — `gather_by_xref` walks the circular's GCN
   cross-reference graph to collect the whole event's circulars.
2. **Aggregate** — `aggregate_event` fuses them into one source: position from
   the discovery circular, photometry unioned across follow-ups, redshift, and
   the **classification from the trained SN-type classifier** (the extractor is
   `RegexExtractor(sn_classifier=…)` when `--model` is given).
3. **Post idempotently** — a session `seen` set (and, live, the source's existing
   SkyPortal photometry via `prime`) means re-seeing an event never re-posts a
   point. Dedup key is `(obj_id, filter, mjd)` — no mag, since SkyPortal converts
   magsys→AB on ingest but preserves filter + mjd.

Because posting is idempotent, the handler is safe to run on every message: each
circular contributes only its *new* points, and the light curve grows over the
stream.

## Sources (`circex/consume/sources.py`)

- **Live:** `gcn_kafka_records()` subscribes to `gcn.circulars` (needs the
  optional `gcn-kafka` dep and GCN client credentials — the `live` extra:
  `pip install -e .[live]`, `GCN_CLIENT_ID`/`GCN_CLIENT_SECRET`).
- **Replay/test:** `replay_dir_records()` + `dir_fetch()` read a directory of
  `{id}.json` circulars — the whole pipeline runs with no Kafka and no network.

## Usage

```bash
# replay a flurry through the full pipeline (dry-run; nothing sent)
circex consume --from-dir flurry/ --model data/models/sn_type.json \
  --default-instrument-id 4 --group-ids 1988

# live, posting to SkyPortal
circex consume --kafka --live --url https://fritz.science/api --token … \
  --group-ids 1988 --default-instrument-id 4 --model data/models/sn_type.json
```

Dry-run by default; `--live` requires a token. On the GRB 260604C flurry replay,
the 20 circulars stream through and the source's 19-point light curve assembles
incrementally, with duplicates skipped (`+N photometry (M already present)`).

## Known follow-ons

- Persistent cross-restart idempotency is handled live by priming `seen` from
  SkyPortal; the replay path is session-only.
- Per-telescope instrument mapping (vs. the generic fallback) via `--instrument-map`.
- Re-aggregating the full event per message is simple + correct but refetches;
  an incremental per-circular attach would cut fetches at higher volume.
