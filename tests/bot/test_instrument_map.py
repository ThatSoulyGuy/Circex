"""Deriving the routing maps from a SkyPortal instance."""

from __future__ import annotations

from circex.bot.instrument_map import (
    derive_bandpass_instrument_map,
    derive_instrument_map,
)

INSTRUMENTS = [
    {
        "id": 1184,
        "name": "FXT",
        "filters": ["epfxt"],
        "telescope": {"name": "Einstein Probe", "nickname": "EP"},
    },
    {
        "id": 1183,
        "name": "WXT",
        "filters": ["epwxt"],
        "telescope": {"name": "Einstein Probe", "nickname": "EP"},
    },
    {
        "id": 42,
        "name": "ALFOSC",
        "filters": ["sdssr", "sdssg"],
        "telescope": {"name": "Nordic Optical Telescope", "nickname": "NOT"},
    },
    {
        "id": 7,
        "name": "DBSP",
        "filters": ["sdssr"],
        "telescope": {"name": "Palomar 5.1m Hale", "nickname": "P200"},
    },
]


def test_a_telescope_with_one_instrument_maps():
    result = derive_instrument_map(INSTRUMENTS)
    assert result["NOT"] == 42
    assert result["Nordic Optical Telescope"] == 42


def test_a_telescope_hosting_several_is_left_out():
    # EP has both WXT and FXT; guessing between them would post to the wrong one.
    result = derive_instrument_map(INSTRUMENTS)
    assert "EP" not in result
    assert "Einstein Probe" not in result


def test_a_mission_bandpass_names_its_instrument():
    result = derive_bandpass_instrument_map(INSTRUMENTS)
    assert result["epfxt"] == 1184
    assert result["epwxt"] == 1183


def test_a_shared_bandpass_is_left_out():
    # sdssr is on dozens of instruments and identifies none of them.
    assert "sdssr" not in derive_bandpass_instrument_map(INSTRUMENTS)
    assert derive_bandpass_instrument_map(INSTRUMENTS)["sdssg"] == 42


def test_records_without_an_id_are_ignored():
    assert derive_instrument_map([{"name": "x", "telescope": {"nickname": "T"}}]) == {}
