"""Harvest silver-labeled SN-type training data from the circular archive.

High-precision weak labeling: a circular gets a type only when it states exactly
one SN type in an SN context, and GRB duration classifications ("type I/II" =
short/long population) are excluded — the same trap the hand gold captures.
Negatives (NONE) are real GRB / afterglow / detection circulars carrying no SN
type, deterministically subsampled so the classifier learns to abstain.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from circex.classify.sn_type import NONE_LABEL

# Type patterns -> canonical label; rare subtypes fold to their family (IIn->II,
# Ic-BL->Ic) so each class has enough support to learn.
_TYPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Ic", re.compile(r"\b(?:broad[- ]lined\s+(?:type\s+)?Ic|type\s+Ic[- ]BL|Ic[- ]BL)\b", re.I)),
    ("Ia", re.compile(r"\b(?:type[- ]?Ia|SNe?\s+Ia|Ia\s+supernova)\b", re.I)),
    ("Ib", re.compile(r"\b(?:type[- ]?Ib|SN\s+Ib)\b(?![/-]?c)", re.I)),
    ("Ic", re.compile(r"\b(?:type[- ]?Ic|SN\s+Ic)\b", re.I)),
    ("II", re.compile(r"\b(?:type[- ]?II[bnP]?|SN\s+II)\b", re.I)),
    ("SLSN", re.compile(r"\b(?:superluminous|SLSN)\b", re.I)),
    ("TDE", re.compile(r"\b(?:tidal disruption|TDE)\b", re.I)),
]
_SN_CTX = re.compile(r"supernova|SNID|classif|spectrum|spectroscop|\bSNe?\b", re.I)
_GRB_DUR = re.compile(
    r"\(short\)|\(long\)|short[- ]duration|long[- ]duration|short/long"
    r"|population|burst.{0,20}type|T_?90",
    re.I,
)
_NONE_CTX = re.compile(r"\b(?:GRB|optical|afterglow|detection|redshift|observ)", re.I)


def label_of(text: str) -> set[str]:
    """SN types stated with SN context; GRB short/long 'type I/II' is excluded."""
    hits: set[str] = set()
    for lab, pattern in _TYPE_PATTERNS:
        for match in pattern.finditer(text):
            ctx = text[max(0, match.start() - 70) : match.end() + 70]
            near = text[max(0, match.start() - 40) : match.end() + 40]
            if lab in ("SLSN", "TDE") or (_SN_CTX.search(ctx) and not _GRB_DUR.search(near)):
                hits.add(lab)
    return hits


def _text_of(record: dict[str, object]) -> str:
    return f"{record.get('subject', '') or ''}\n{record.get('body', '') or ''}"


def harvest_training_data(
    archive_dir: Path,
    *,
    none_ratio: int = 3,
    min_none_len: int = 200,
    exclude_ids: set[int] | None = None,
) -> list[tuple[str, str]]:
    """(text, label) pairs from the archive: single-type positives + NONE sample.

    NONE is sampled by a deterministic stride over sorted circular ids, targeting
    `none_ratio`x the positive count, so the negative class teaches abstention
    without swamping the positives. `exclude_ids` (e.g. the eval gold) are held
    out so the classifier is never trained on what it will be tested against.
    """
    exclude_ids = exclude_ids or set()
    positives: list[tuple[str, str]] = []
    none_ids: list[tuple[int, str]] = []
    for path in sorted(archive_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if int(record.get("circularId") or 0) in exclude_ids:
            continue
        text = _text_of(record)
        labels = label_of(text)
        if len(labels) == 1:
            positives.append((text, next(iter(labels))))
        elif not labels and _NONE_CTX.search(text) and len(text) >= min_none_len:
            none_ids.append((int(record.get("circularId") or 0), text))

    none_ids.sort(key=lambda pair: pair[0])
    target = max(1, none_ratio * len(positives))
    stride = max(1, len(none_ids) // target)
    sampled = none_ids[::stride][:target]
    return positives + [(text, NONE_LABEL) for _, text in sampled]
