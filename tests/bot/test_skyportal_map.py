"""Tests for the CircularExtraction -> SkyPortal mapping (docs/design_skyportal_bot.md)."""

from __future__ import annotations

from circex.bot import to_actions
from circex.bot.poster import SkyPortalPoster
from circex.schema import (
    CircularExtraction,
    Event,
    ExtractionMeta,
    Localization,
    PhotometryExt,
    Redshift,
    Span,
)


def _meta() -> ExtractionMeta:
    return ExtractionMeta(extractor="regex-v1")


def test_source_from_event_and_localization() -> None:
    ex = CircularExtraction(
        circular_id=1,
        event=Event(event_name="GRB 260608A"),
        localization=Localization(ra=224.5, dec=28.8),
        extraction_meta=_meta(),
    )
    a = to_actions(ex)
    assert a.source is not None
    assert a.source.to_payload() == {"id": "GRB260608A", "ra": 224.5, "dec": 28.8}


def test_no_source_without_event_name() -> None:
    ex = CircularExtraction(circular_id=1, extraction_meta=_meta())
    assert to_actions(ex).source is None


def test_prefers_optical_at_name_for_obj_id() -> None:
    ex = CircularExtraction(
        circular_id=1,
        event=Event(event_name=["GW170817", "AT2017gfo"]),
        extraction_meta=_meta(),
    )
    assert to_actions(ex).source.id == "AT2017gfo"


def test_timed_photometry_becomes_a_point() -> None:
    ex = CircularExtraction(
        circular_id=7,
        event=Event(event_name="AT2026xyz"),
        photometry=[
            PhotometryExt(filter="r", bandpass="sdssr", mag=20.4, mag_error=0.05,
                          mag_system="AB", obs_mjd=61199.0, telescope="NOT")
        ],
        extraction_meta=_meta(),
    )
    a = to_actions(ex, instrument_map={"NOT": 7})
    assert len(a.photometry) == 1
    p = a.photometry[0].to_payload()
    assert p["mjd"] == 61199.0 and p["filter"] == "sdssr" and p["magsys"] == "ab"
    assert p["mag"] == 20.4 and p["magerr"] == 0.05 and p["instrument_id"] == 7


def test_untimed_photometry_is_not_posted_but_noted() -> None:
    ex = CircularExtraction(
        circular_id=1,
        event=Event(event_name="AT2026xyz"),
        photometry=[PhotometryExt(filter="r", bandpass="sdssr", mag=20.4)],  # no obs_mjd
        extraction_meta=_meta(),
    )
    a = to_actions(ex)
    assert a.photometry == []
    assert a.skipped_rows == 1
    assert any("could not be posted" in c for c in a.comments)


def test_non_detection_maps_to_limiting_mag() -> None:
    ex = CircularExtraction(
        circular_id=1,
        event=Event(event_name="AT2026xyz"),
        photometry=[PhotometryExt(filter="r", bandpass="sdssr", limiting_mag=22.5,
                                  mag_system="AB", obs_mjd=61199.0)],
        extraction_meta=_meta(),
    )
    p = to_actions(ex).photometry[0].to_payload()
    assert p["mag"] is None and p["limiting_mag"] == 22.5


def test_scalar_redshift_becomes_patch_and_comment() -> None:
    ex = CircularExtraction(
        circular_id=1,
        event=Event(event_name="AT2026xyz"),
        redshift=Redshift(redshift=0.5, redshift_error=0.01),
        provenance={"redshift": Span(start=0, end=7, snippet="z = 0.5")},
        extraction_meta=_meta(),
    )
    a = to_actions(ex)
    assert a.redshift == (0.5, 0.01)
    assert any("Redshift z=0.5" in c for c in a.comments)


def test_bound_redshift_is_a_comment_not_a_value() -> None:
    ex = CircularExtraction(
        circular_id=1,
        event=Event(event_name="AT2026xyz"),
        extraction_meta=ExtractionMeta(extractor="regex-v1", notes=["redshift_bound: z <= 1.61"]),
    )
    a = to_actions(ex)
    assert a.redshift is None
    assert any("redshift_bound" in c for c in a.comments)


def test_provenance_lands_in_photometry_altdata() -> None:
    ex = CircularExtraction(
        circular_id=42,
        event=Event(event_name="AT2026xyz"),
        photometry=[PhotometryExt(filter="r", bandpass="sdssr", mag=20.4, obs_mjd=61199.0)],
        provenance={"photometry[0]": Span(start=0, end=5, snippet="r=20.4")},
        extraction_meta=_meta(),
    )
    alt = to_actions(ex).photometry[0].to_payload()["altdata"]
    assert alt["note"] == 'photometry[0]: "r=20.4"'
    assert alt["circex_circular_id"] == 42


def test_unmapped_telescope_flagged_not_guessed() -> None:
    ex = CircularExtraction(
        circular_id=1,
        event=Event(event_name="AT2026xyz"),
        photometry=[PhotometryExt(filter="r", bandpass="sdssr", mag=20.4, obs_mjd=61199.0,
                                  telescope="VLT")],
        extraction_meta=_meta(),
    )
    p = to_actions(ex, instrument_map={}).photometry[0].to_payload()  # empty map
    assert "instrument_id" not in p  # None -> omitted
    assert p["altdata"]["unmapped_telescope"] == "VLT"


def test_dry_run_poster_sends_nothing_and_plans_in_order() -> None:
    ex = CircularExtraction(
        circular_id=1,
        event=Event(event_name="AT2026xyz"),
        localization=Localization(ra=10.0, dec=20.0),
        photometry=[PhotometryExt(filter="r", bandpass="sdssr", mag=20.4, obs_mjd=61199.0)],
        redshift=Redshift(redshift=0.5),
        extraction_meta=_meta(),
    )
    plan = SkyPortalPoster().post(to_actions(ex))  # dry-run (no token)
    methods = [(r["method"], r["path"]) for r in plan]
    assert methods[0] == ("POST", "/sources")
    assert ("POST", "/photometry") in methods
    assert ("PATCH", "/sources/AT2026xyz") in methods


def test_live_post_requires_token() -> None:
    ex = CircularExtraction(circular_id=1, event=Event(event_name="AT2026xyz"),
                            extraction_meta=_meta())
    # live=True but no token -> still dry-run (returns plan, sends nothing)
    plan = SkyPortalPoster(live=True, token=None).post(to_actions(ex))
    assert isinstance(plan, list)
