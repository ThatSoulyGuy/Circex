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
    actions = aggregate_event(records, RegexExtractor(), default_instrument_id=7, group_ids=[3])
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
        40001: {
            "circularId": 40001,
            "subject": "s",
            "body": "See Smith, GCN 40002; Jones, GCN 40003.",
        },
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


def test_source_created_from_name_and_position_without_surviving_photometry() -> None:
    """A named counterpart with a position is a source even when its photometry
    row is unpostable (e.g. no obs_mjd) — the source must not depend on a
    surviving photometry point (live-consumer regression, GCN 45198)."""

    class _NoMjdExtractor:
        """Yields a position + a photometry row that can never post (no obs_mjd)."""

        extractor_id = "test"

        def extract(self, circ):  # noqa: ANN001
            from circex.schema import CircularExtraction

            return CircularExtraction.model_validate(
                {
                    "circular_id": circ.circular_id,
                    "event": {"event_name": "AT2026vts"},
                    "localization": {"ra": 191.3, "dec": 30.6},
                    "photometry": [{"filter": "r", "mag": 19.78}],  # no obs_mjd -> skipped
                    "extraction_meta": {"extractor": "test"},
                }
            )

    rec = {"circularId": 45198, "subject": "candidate", "body": "counterpart AT2026vts"}
    actions = aggregate_event([rec], _NoMjdExtractor(), default_instrument_id=4, group_ids=[1])
    assert actions.source is not None  # the bug: this was None
    assert actions.source.id == "AT2026vts"
    assert actions.source.ra == 191.3 and actions.source.dec == 30.6
    assert actions.skipped_rows == 1  # the row was still (correctly) unpostable


def test_skip_reasons_survive_aggregation():
    """A row dropped in one circular must still be reportable on the event.

    The comment on the event is built from the aggregate; a reason lost here is
    a measurement that vanishes without explanation.
    """
    from circex.bot.aggregate import aggregate_event
    from circex.extract.protocol import Circular
    from circex.schema import (
        CircularExtraction,
        Event,
        ExtractionMeta,
        Localization,
        PhotometryExt,
    )

    class _Ext:
        extractor_id = "stub"

        def extract(self, circular: Circular):
            return CircularExtraction(
                circular_id=circular.circular_id,
                event=Event(event_name="GRB 260903A"),
                localization=Localization(ra=10.0, dec=20.0),
                photometry=[PhotometryExt(filter="Zband", mag=19.0, obs_mjd=61286.0)],
                extraction_meta=ExtractionMeta(extractor="stub"),
            )

    actions = aggregate_event(
        [{"circularId": 1, "subject": "s", "body": "b"}],
        _Ext(),
        default_instrument_id=1,
    )
    assert actions.skipped_reasons
    assert "no bandpass" in actions.skipped_reasons


def test_a_retraction_withdraws_the_event_photometry():
    """GCN 45503 retracted the counterpart GCN 45501 reported.

    The retraction cross-references the circular it withdraws, so the aggregate
    contains both; posting the withdrawn rows again is the one thing it must not
    do.
    """
    from circex.bot.aggregate import aggregate_event
    from circex.extract.protocol import Circular
    from circex.schema import (
        CircularExtraction,
        Event,
        ExtractionMeta,
        Localization,
        PhotometryExt,
    )

    class _Ext:
        extractor_id = "stub"

        def extract(self, circular: Circular):
            retracting = circular.circular_id == 45503
            return CircularExtraction(
                circular_id=circular.circular_id,
                event=Event(event_name="GRB 260903A"),
                localization=Localization(ra=25.77, dec=11.44),
                retraction=retracting,
                photometry=[]
                if retracting
                else [PhotometryExt(filter="r", bandpass="sdssr", mag=17.91, obs_mjd=61286.55)],
                extraction_meta=ExtractionMeta(extractor="stub"),
            )

    records = [
        {"circularId": 45503, "subject": "Retraction of optical counterpart", "body": "b"},
        {"circularId": 45501, "subject": "LCO optical counterpart", "body": "b"},
    ]
    actions = aggregate_event(records, _Ext(), default_instrument_id=1)
    assert actions.photometry == []
    assert any("withdraws this counterpart" in c for c in actions.comments)
