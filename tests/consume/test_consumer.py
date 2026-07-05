"""Tests for the live consumer (circex/consume)."""

from __future__ import annotations

from circex.bot.poster import SkyPortalPoster
from circex.classify import SNTypeClassifier
from circex.consume import run
from circex.extract.protocol import Circular
from circex.extract.regex import RegexExtractor

_DISCOVERY = {
    "circularId": 1,
    "subject": "GRB 010101A: discovery",
    "body": "GRB 010101A optical counterpart at RA = 150.0, Dec = +20.0 (J2000). See GCN 2.",
}
_FOLLOWUP = {
    "circularId": 2,
    "subject": "GRB 010101A: follow-up",
    "body": "GRB 010101A observed on 2024-01-02 03:00 UTC, r = 19.5 +/- 0.05. As in GCN 1.",
}


def test_consumer_streams_event_and_dedups() -> None:
    records = {1: _DISCOVERY, 2: _FOLLOWUP}

    def fetch(cid: int):
        return records.get(cid)

    results = run(
        iter([_DISCOVERY, _FOLLOWUP]),
        extractor=RegexExtractor(),
        poster=SkyPortalPoster(),  # dry-run
        fetch=fetch,
        group_ids=[3],
        default_instrument_id=7,
    )
    # first circular aggregates the event and posts the r-band point;
    # the second re-aggregates the same event -> idempotently skipped.
    assert results[0].status == "posted" and results[0].photometry_posted == 1
    assert results[1].photometry_posted == 0 and results[1].photometry_skipped == 1


def test_extractor_uses_sn_classifier_and_abstains() -> None:
    clf = SNTypeClassifier.fit(
        [
            "the transient is a type Ia supernova classified with SNID",
            "type Ia supernova spectrum near maximum",
            "GRB 200101A optical afterglow detection r = 20, no classification",
        ],
        ["Ia", "Ia", "NONE"],
        min_count=1,
    )
    ext = RegexExtractor(sn_classifier=clf)
    typed = ext.extract(
        Circular(circular_id=1, subject="", body="a clear type Ia supernova from SNID")
    )
    assert typed.classification is not None and typed.classification.classification == "Ia"
    untyped = ext.extract(
        Circular(circular_id=2, subject="", body="GRB 200103A optical afterglow detection r = 20")
    )
    assert untyped.classification is None  # classifier abstains where regex would over-fire
