"""Tests for event aggregation (circex/bot/aggregate.py)."""

from __future__ import annotations

from circex.bot import aggregate_event, gather_by_xref
from circex.extract.regex import RegexExtractor


def test_aggregate_fuses_position_and_photometry() -> None:
    """Position from the discovery circular; photometry from the follow-up, attributed."""
    records = [
        {
            "circularId": 40010,
            "subject": "GRB 990102A: discovery",
            "body": "GRB 990102A optical counterpart at RA = 150.0, Dec = +20.0 (J2000).",
        },
        {
            "circularId": 40011,
            "subject": "GRB 990102A: follow-up",
            "body": "We observed GRB 990102A on 2024-01-02 03:00 UTC, measured r = 19.5 +/- 0.05.",
        },
    ]
    actions = aggregate_event(
        records, RegexExtractor(), default_instrument_id=7, group_ids=[3]
    )
    assert actions.source is not None
    assert actions.source.id == "GRB990102A"
    assert actions.source.ra == 150.0 and actions.source.dec == 20.0
    assert len(actions.photometry) == 1
    point = actions.photometry[0]
    assert point.obj_id == "GRB990102A" and point.filter == "sdssr"
    assert point.altdata["circex_circular_id"] == 40011  # attributed to the follow-up


def test_aggregate_dedups_identical_points() -> None:
    """The same circular seen twice must not double-post its photometry."""
    rec = {
        "circularId": 40020,
        "subject": "GRB 990102A",
        "body": (
            "GRB 990102A at RA = 10.0, Dec = +5.0. "
            "Observed 2024-01-02 03:00 UTC, r = 19.5 +/- 0.05."
        ),
    }
    actions = aggregate_event([rec, rec], RegexExtractor(), default_instrument_id=7, group_ids=[3])
    assert len(actions.photometry) == 1


def test_aggregate_no_position_yields_no_source() -> None:
    """With no circular carrying a position, no source is created."""
    rec = {
        "circularId": 40030,
        "subject": "GRB 990102A",
        "body": "We observed GRB 990102A on 2024-01-02 03:00 UTC, r = 19.5 +/- 0.05.",
    }
    actions = aggregate_event([rec], RegexExtractor(), default_instrument_id=7, group_ids=[3])
    assert actions.source is None


def test_gather_by_xref_walks_the_citation_graph() -> None:
    db = {
        40001: {"circularId": 40001, "subject": "s",
                "body": "See Smith, GCN 40002; Jones, GCN 40003."},
        40002: {"circularId": 40002, "subject": "c2", "body": "as in GCN 40003"},
        40003: {"circularId": 40003, "subject": "c3", "body": "discovery"},
    }
    got = gather_by_xref(40001, lambda cid: db.get(cid), max_hops=1)
    assert sorted(r["circularId"] for r in got) == [40001, 40002, 40003]


def test_gather_by_xref_tolerates_404() -> None:
    db = {40001: {"circularId": 40001, "subject": "seed", "body": "cites GCN 40099 (missing)"}}
    got = gather_by_xref(40001, lambda cid: db.get(cid), max_hops=1)
    assert [r["circularId"] for r in got] == [40001]


def test_aggregate_prefers_refined_position_over_coarse_trigger() -> None:
    """The optical-counterpart position must win over a coarse gamma-ray trigger box."""
    records = [
        {
            "circularId": 1,
            "subject": "GRB 010101A: Fermi GBM Final Real-time Localization",
            "body": "The Fermi GBM team reports GRB 010101A at RA = 220.5, Dec = +33.4 (J2000).",
        },
        {
            "circularId": 2,
            "subject": "GRB 010101A: MASTER OT optical counterpart discovery",
            "body": (
                "We discovered the optical counterpart (OT) at RA = 224.456, Dec = +28.817. "
                "Observed on 2024-01-02 03:00 UTC at r = 19.5 +/- 0.05."
            ),
        },
    ]
    actions = aggregate_event(records, RegexExtractor(), group_ids=[3], default_instrument_id=7)
    assert actions.source is not None
    assert abs(actions.source.ra - 224.456) < 0.01  # OT, not the coarse GBM box (220.5)
