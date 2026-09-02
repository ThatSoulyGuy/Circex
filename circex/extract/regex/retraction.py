"""Detects a circular that withdraws an earlier trigger.

A retraction still names the event and often restates its position, so an
extraction that ignores the withdrawal reads as a fresh detection downstream.
"""

from __future__ import annotations

import re

# Anchored on the subject line, where a retraction announces itself. Matching the
# body instead picks up the "false alarm rate" boilerplate that every IceCube
# alert carries.
_RETRACTION_RE = re.compile(
    r"\bis\s+not\s+a\s+(?:GRB|burst|real|astrophysical)"
    r"|\bnot\s+astrophysical"
    r"|\bprobably\s+a\s+noise"
    r"|\bconsistent\s+with\s+noise"
    r"|\bretract(?:ion|ed|ing|s)?\b"
    r"|\bspurious\b"
    r"|\bnot\s+a\s+real\s+(?:event|source|transient)"
    r"|\bno\s+longer\s+believe"
    r"|\bnot\s+of\s+astrophysical\s+origin",
    re.I,
)


def is_retraction(subject: str | None) -> bool:
    """Whether the subject line withdraws a previously reported trigger."""
    return bool(subject and _RETRACTION_RE.search(subject))
