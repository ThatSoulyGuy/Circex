"""Canonical prompt template for the LLM extractors.

The template is split into:
- system text: role + schema explanation + extraction policy. Stable across calls
  so it benefits from Anthropic prompt caching (cache_control: ephemeral).
- few-shot examples: 4 hand-crafted (circular body, extraction JSON) pairs covering
  multi-row mag tables, in-prose classification, upper limits, and GCN cross-refs.
  GW-counterpart stratum deliberately UNSEEN so we measure generalization on the
  fifth stratum at eval time.
- user message: the actual circular body to extract.

Bumping PROMPT_V1 invalidates the LLM cache cleanly. See docs/prompt_deltas.md
for what changed vs Vidushi's published prompt (Sharma et al. 2025).
"""

from __future__ import annotations

import json
from typing import Any, TypedDict

from circex.extract.protocol import Circular
from circex.schema import CircularExtraction

PROMPT_V1 = "2026-06-04"


class Message(TypedDict):
    role: str
    content: str


# ---------- System prompt ----------

SYSTEM_TEMPLATE = """You are an information-extraction system for GCN Circulars \
(astronomical observation reports for transient events).

Your job: given the free text of one circular, emit a single structured \
extraction conforming to the schema below. Call the `submit_extraction` tool \
exactly once with the structured object.

POLICY:
- Extract ONLY what the circular explicitly states. Use null when a field is \
not stated. Never guess. Never fill in plausible defaults.
- Coordinates: always store as decimal degrees, ICRS J2000.
- Multi-row magnitude tables: emit one `photometry[]` row per (filter, epoch).
- Mag system inference:
    Sloan filters (g, r, i, z, y) default to AB.
    Bessel filters (U, B, V, R, I) default to Vega.
    NIR filters (J, H, K, Ks) are Vega.
    Leave null when genuinely unstated and not inferable.
- Canonical bandpass: also set `photometry[].bandpass` to the sncosmo/SkyPortal \
name for the filter when recognizable. Sloan u/g/r/i/z -> sdss{u,g,r,i,z}; \
y -> ps1::y; Bessel U/B/V/R/I -> bessell{u,b,v,r,i}; NIR J/H/K/Ks -> \
2mass{j,h,ks}. Leave null for unfiltered/clear or unknown filters. Always keep \
the raw `filter` string as written.
- T+offset phrasings (e.g., "T+234s") are LITERAL captures in `time_offsets[]`; \
do NOT resolve against the absolute trigger time.
- Classification: must be a canonical class name from the time-domain taxonomy. \
If the circular's classification term is an alias (e.g., "SNIa"), emit the \
canonical name ("Ia"). If you are not confident, leave null.
- GCN cross-references (e.g., "GCN #12345") populate `follow_up.reference`.
- The reporter is the *alerting party*, NOT the photometry telescope. Most \
optical observation circulars do not need to populate reporter.
- DO NOT populate `extraction_meta` other than `notes` (see below).
- BOUND REDSHIFTS: when the circular states only an inequality on z (e.g. \
"z <= 1.61", "z =< 1.61", "z >= 0.2"), leave `redshift` as null AND append \
the literal phrase to `extraction_meta.notes` as \
`"redshift_bound: <verbatim phrase>"`. Add a `_redshift_bound` provenance \
entry pointing at the source span. Never coerce a bound into the \
Redshift point-value schema.
- PROVENANCE: for every field you populate, also add an entry to `provenance` \
keyed by the dotted field path that points at the source-text span you used. \
The value is `{"start": <int>, "end": <int>, "snippet": <str>}` where `start` \
and `end` are character offsets into the circular body and `snippet` is the \
literal `body[start:end]` substring. Prefer leaf-level keys when one specific \
phrase justifies the value (e.g., `"redshift.redshift"` pointing at \
`"z = 0.215"`, `"photometry[0].mag"` pointing at `"20.42"`); fall back to \
object-level keys (`"redshift"`, `"photometry[0]"`) when a single contiguous \
range covers the whole subobject. Omit `provenance` entries for fields you do \
not populate. If you cannot localize a value to a contiguous span (e.g., it \
was inferred from a discontinuous combination of phrases), leave it out of \
`provenance` rather than guessing offsets.

OUTPUT: exactly one call to `submit_extraction` with the structured object."""


def build_system_text() -> str:
    """Return the full system text (constant across calls; cache-friendly)."""
    return SYSTEM_TEMPLATE


# ---------- Few-shot examples ----------
# Each example: a (circular_body, extraction) pair. Crafted to cover one stratum
# each from {multi-row mag, in-prose classification, upper limit, GCN cross-ref}.

_FEW_SHOTS: list[tuple[str, dict[str, Any]]] = [
    # 1) Multi-row magnitude table.
    (
        """GRB 240101A: NOT optical observations

We observed the field of GRB 240101A with the ALFOSC instrument on the NOT.
Photometry calibrated against PS1:

  Date            Filter   Mag     Err
  2024-01-02 04:30  r        20.42  0.05
  2024-01-02 05:10  r        20.55  0.05
  2024-01-02 05:50  g        21.10  0.07

Seeing was 1.1 arcsec; airmass 1.3.""",
        {
            "circular_id": 0,
            "event": {"event_name": "GRB 240101A"},
            "photometry": [
                {"filter": "r", "bandpass": "sdssr", "mag": 20.42, "mag_error": 0.05,
                 "mag_system": "AB", "telescope": "NOT", "instrument": "ALFOSC",
                 "calibration_reference": "PS1", "seeing": 1.1, "airmass": 1.3},
                {"filter": "r", "bandpass": "sdssr", "mag": 20.55, "mag_error": 0.05,
                 "mag_system": "AB", "telescope": "NOT", "instrument": "ALFOSC",
                 "calibration_reference": "PS1", "seeing": 1.1, "airmass": 1.3},
                {"filter": "g", "bandpass": "sdssg", "mag": 21.10, "mag_error": 0.07,
                 "mag_system": "AB", "telescope": "NOT", "instrument": "ALFOSC",
                 "calibration_reference": "PS1", "seeing": 1.1, "airmass": 1.3},
            ],
        },
    ),
    # 2) In-prose classification + redshift, with leaf-level provenance.
    (
        """AT2024xyz: classification as a Type Ic-BL supernova

Spectroscopy with the VLT/X-shooter on 2024-03-15 reveals broad lines typical
of a Ic-BL supernova. Host galaxy emission lines yield z = 0.215 +/- 0.001.""",
        {
            "circular_id": 0,
            "event": {"event_name": "AT2024xyz"},
            "classification": {"classification": "Ic-BL"},
            "redshift": {
                "redshift": 0.215,
                "redshift_error": 0.001,
                "redshift_measure": "spectroscopic",
                "redshift_type": "host",
            },
            "provenance": {
                "event": {"start": 0, "end": 9, "snippet": "AT2024xyz"},
                "classification": {"start": 136, "end": 141, "snippet": "Ic-BL"},
                "redshift.redshift": {"start": 186, "end": 195, "snippet": "z = 0.215"},
                "redshift.redshift_error": {"start": 200, "end": 205, "snippet": "0.001"},
            },
        },
    ),
    # 3) Photometric upper limit.
    (
        """GRB 240505B: GOTO non-detection

We observed the GRB 240505B field with GOTO starting T+450 s after the BAT
trigger. No source is detected; 3-sigma upper limit is L > 19.5 in unfiltered
white light (clear).""",
        {
            "circular_id": 0,
            "event": {"event_name": "GRB 240505B"},
            "time_offsets": [{"value": 450.0, "unit": "s", "reference": "T+"}],
            "photometry": [
                {"filter": "clear", "limiting_mag": 19.5, "limiting_mag_sigma": 3.0,
                 "telescope": "GOTO"},
            ],
        },
    ),
    # 4) GCN cross-references + counterpart-of relation.
    (
        """AT2017gfo: optical counterpart confirmation

Following GCN Circular 21505, we report continued imaging of the optical
counterpart to GW170817 (LVK trigger S190425z is unrelated). See also GCN
#21509 and GCN #21512 for prior reports.""",
        {
            "circular_id": 0,
            "event": {"event_name": ["AT2017gfo", "GW170817"]},
            "follow_up": {
                "ref_type": "GW",
                "ref_instrument": "LVK",
                "ref_ID": "GW170817",
                "reference": {"gcn_circulars": "21505,21509,21512"},
            },
        },
    ),
]


def _render_few_shots() -> list[Message]:
    """Render the few-shots as a sequence of user/assistant messages."""
    msgs: list[Message] = []
    for body, extraction in _FEW_SHOTS:
        msgs.append({"role": "user", "content": _format_user_message(body)})
        msgs.append(
            {
                "role": "assistant",
                "content": (
                    "<call submit_extraction with input:>\n"
                    + json.dumps(extraction, indent=2)
                ),
            }
        )
    return msgs


# ---------- User message rendering ----------


def _format_user_message(body: str) -> str:
    return f"<circular>\n{body}\n</circular>"


def build_messages(circular: Circular) -> list[Message]:
    """Build the few-shot + final-user messages list (Anthropic/Ollama compatible).

    The system text is passed separately to Anthropic; for Ollama it can be the
    first message if needed by the caller.
    """
    msgs = list(_render_few_shots())
    msgs.append({"role": "user", "content": _format_user_message(circular.body)})
    return msgs


def llm_input_schema() -> dict[str, Any]:
    """JSON Schema for `submit_extraction` tool input.

    CircularExtraction with `extraction_meta` reduced to a notes-only stub: the
    runner fills the run-level fields (model, tokens, cost, latency), but the
    model may populate `extraction_meta.notes` for facts the schema can't
    represent — most importantly bound redshifts (`"redshift_bound: z <= 1.61"`).
    Exposing the slot is what lets the bound-redshift convention actually reach
    the model on both the Claude (tool-schema) and Ollama (embedded-schema) paths.
    """
    schema = CircularExtraction.model_json_schema()
    props = schema.get("properties", {})
    # Replace the full ExtractionMeta $ref with an inline notes-only object so
    # the model can set notes but not the runner-owned fields.
    props["extraction_meta"] = {
        "type": "object",
        "properties": {
            "notes": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Annotations for facts the schema can't represent. For a "
                    "bound redshift, leave `redshift` null and add "
                    "\"redshift_bound: <verbatim phrase>\" here."
                ),
            }
        },
        "description": "Set ONLY `notes`; the runner fills the rest.",
    }
    required = schema.get("required", [])
    schema["required"] = [k for k in required if k != "extraction_meta"]
    return schema
