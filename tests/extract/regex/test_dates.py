"""Tests for date / T+offset parsers."""

from __future__ import annotations

from circex.extract.regex.dates import parse_time_offsets


def test_t_plus_seconds() -> None:
    offsets = parse_time_offsets("Observations began at T+234s.")
    assert len(offsets) == 1
    o = offsets[0]
    assert o.value == 234.0
    assert o.unit == "s"
    assert o.reference == "T+"


def test_t_minus_seconds() -> None:
    offsets = parse_time_offsets("Pre-trigger frame at T-30 s.")
    assert len(offsets) == 1
    assert offsets[0].value == -30.0
    assert offsets[0].reference == "T-"


def test_t_plus_hours() -> None:
    offsets = parse_time_offsets("T+8.5 hours after burst.")
    assert any(o.value == 8.5 and o.unit == "h" for o in offsets)


def test_post_trigger_phrasing() -> None:
    offsets = parse_time_offsets("4 hours after the trigger we observed.")
    assert any(o.value == 4.0 and o.unit == "h" and o.reference == "trigger" for o in offsets)


def test_multiple_offsets() -> None:
    text = "First epoch at T+100s, second at T+30 minutes, third at T+2 hours."
    offsets = parse_time_offsets(text)
    units = [o.unit for o in offsets]
    assert "s" in units and "m" in units and "h" in units


def test_no_offsets() -> None:
    assert parse_time_offsets("No time offsets mentioned here.") == []


def test_elapsed_time_written_as_a_difference():
    """ "T-To=11h" states the same offset as "11 hours after the trigger"."""
    assert [(o.value, o.unit, o.reference) for o in parse_time_offsets("mid-time at T-To=11h")] == [
        (11.0, "h", "trigger")
    ]
    assert [(o.value, o.unit, o.reference) for o in parse_time_offsets("t-t0 = 2.30 hr")] == [
        (2.3, "h", "trigger")
    ]
