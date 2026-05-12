"""Stratified iteration-subset construction for Sprint 1-2 labeling work.

Per PDF Phase 1 item: stratify across five circular strata:
  (a) single-row magnitude report
  (b) multi-row magnitude table
  (c) spectroscopic classification with redshift
  (d) photometric upper limit
  (e) GW/neutrino counterpart announcement

The classifier here is a lightweight keyword heuristic — good enough to bootstrap
a labeling subset; the LLM and regex extractors handle the real extraction later.
"""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

Stratum = Literal[
    "single_row_mag",
    "multi_row_mag_table",
    "spec_z_classification",
    "photometric_upper_limit",
    "gw_neutrino_counterpart",
]

ALL_STRATA: tuple[Stratum, ...] = (
    "single_row_mag",
    "multi_row_mag_table",
    "spec_z_classification",
    "photometric_upper_limit",
    "gw_neutrino_counterpart",
)


@dataclass(frozen=True)
class StratifiedCircular:
    circular_id: int
    stratum: Stratum


_MULTIROW_TABLE_RE = re.compile(
    r"(?:date|mjd|epoch).{0,40}(?:filter|band).{0,40}(?:mag|magnitude)",
    re.IGNORECASE | re.DOTALL,
)
_UPPER_LIMIT_RE = re.compile(
    r"\b(\d+(?:\.\d+)?\s*[-–]?\s*sigma\s+upper\s+limit|>\s*\d{1,2}\.\d|m\s*>\s*\d{1,2})",
    re.IGNORECASE,
)
_SPEC_Z_RE = re.compile(
    r"\bspectro(?:scopic|scopy|metry|graph).{0,200}(?:z\s*[=~≈]\s*\d|redshift\s+of\s+\d)",
    re.IGNORECASE | re.DOTALL,
)
_GW_NEUTRINO_RE = re.compile(
    r"\b(?:gw\s?\d{6}|s\d{6}|icecube[-\s]?\d|counterpart\s+to\s+(?:gw|the\s+gw|the\s+neutrino))",
    re.IGNORECASE,
)
_SINGLE_MAG_RE = re.compile(
    r"\b(?:r|g|i|R|I|V|B|U|J|H|K|clear)\s*[=~]\s*\d{1,2}\.\d",
)


def classify_stratum(body: str) -> Stratum | None:
    """Heuristic single-stratum tag for one circular body. Returns None if no fit."""
    if _MULTIROW_TABLE_RE.search(body):
        return "multi_row_mag_table"
    if _GW_NEUTRINO_RE.search(body):
        return "gw_neutrino_counterpart"
    if _SPEC_Z_RE.search(body):
        return "spec_z_classification"
    if _UPPER_LIMIT_RE.search(body):
        return "photometric_upper_limit"
    if _SINGLE_MAG_RE.search(body):
        return "single_row_mag"
    return None


def build_stratified_subset(
    circulars: list[dict[str, Any]],
    per_stratum: int = 100,
    seed: int = 42,
) -> list[StratifiedCircular]:
    """Pick up to `per_stratum` circulars per stratum from the input pool.

    `circulars` should be a list of dicts with `circularId` and `body` fields.
    Returns a list of StratifiedCircular; ordering is by stratum then circular_id.
    """
    rng = random.Random(seed)
    by_stratum: dict[Stratum, list[int]] = defaultdict(list)

    for record in circulars:
        try:
            cid = int(record["circularId"])
        except (KeyError, TypeError, ValueError):
            continue
        body = record.get("body") or ""
        stratum = classify_stratum(body)
        if stratum is None:
            continue
        by_stratum[stratum].append(cid)

    out: list[StratifiedCircular] = []
    for stratum in ALL_STRATA:
        pool = by_stratum.get(stratum, [])
        rng.shuffle(pool)
        for cid in sorted(pool[:per_stratum]):
            out.append(StratifiedCircular(circular_id=cid, stratum=stratum))
    return out


def save_subset(subset: list[StratifiedCircular], path: Path) -> None:
    """Persist a subset to JSON for reproducibility."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [{"circular_id": s.circular_id, "stratum": s.stratum} for s in subset]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_subset(path: Path) -> list[StratifiedCircular]:
    """Load a previously-saved stratified subset."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        StratifiedCircular(circular_id=item["circular_id"], stratum=item["stratum"])
        for item in payload
    ]
