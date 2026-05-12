"""Tests for circex.extract.regex.regex_events (ported from GCNMCP tests/test_utils.py)."""

from circex.extract.regex.regex_events import (
    clean_text,
    extract_event_from_query,
    extract_events,
    extract_matches,
    normalize_event,
)

# ── clean_text ────────────────────────────────────────────────────────────────


def test_clean_text_none_returns_empty_string() -> None:
    assert clean_text(None) == ""


def test_clean_text_empty_string_returns_empty_string() -> None:
    assert clean_text("") == ""


def test_clean_text_strips_leading_trailing_whitespace() -> None:
    assert clean_text("  hello  ") == "hello"


def test_clean_text_removes_null_bytes() -> None:
    assert clean_text("GRB\x00260120B") == "GRB 260120B"


def test_clean_text_strips_and_removes_null_bytes_together() -> None:
    assert clean_text("  GRB\x00260120B  ") == "GRB 260120B"


def test_clean_text_preserves_internal_whitespace() -> None:
    assert clean_text("GRB 260120B: refined analysis") == "GRB 260120B: refined analysis"


# ── normalize_event ───────────────────────────────────────────────────────────


def test_normalize_event_removes_spaces() -> None:
    assert normalize_event("GRB 260120B") == "GRB260120B"


def test_normalize_event_uppercases() -> None:
    assert normalize_event("ep260119a") == "EP260119A"


def test_normalize_event_removes_internal_whitespace() -> None:
    assert normalize_event("GRB  260120 B") == "GRB260120B"


def test_normalize_event_none_returns_none() -> None:
    assert normalize_event(None) is None


def test_normalize_event_empty_string_returns_none() -> None:
    assert normalize_event("") is None


# ── extract_matches ───────────────────────────────────────────────────────────


def test_extract_matches_finds_grb() -> None:
    assert extract_matches("GRB 260120B was detected.") == ["GRB260120B"]


def test_extract_matches_finds_grb_without_space() -> None:
    assert extract_matches("Detection of GRB260120B in optical.") == ["GRB260120B"]


def test_extract_matches_finds_ep_event() -> None:
    assert extract_matches("EP260119a follow-up observations.") == ["EP260119A"]


def test_extract_matches_finds_swift_j() -> None:
    result = extract_matches("Swift J1234.5+6789.0 was triggered.")
    assert any("SWIFTJ" in r for r in result)


def test_extract_matches_returns_events_in_text_order() -> None:
    text = "We compare GRB 260120B with EP260119a and GRB250101A."
    result = extract_matches(text)
    assert result == ["GRB260120B", "EP260119A", "GRB250101A"]


def test_extract_matches_deduplicates() -> None:
    text = "GRB 260120B was detected. Later GRB260120B was analyzed."
    assert extract_matches(text) == ["GRB260120B"]


def test_extract_matches_case_insensitive() -> None:
    assert extract_matches("grb 260120b is interesting.") == ["GRB260120B"]


def test_extract_matches_no_event_returns_empty() -> None:
    assert extract_matches("We observed the field and found nothing.") == []


# ── extract_events ────────────────────────────────────────────────────────────


def test_extract_events_prefers_event_id() -> None:
    record = {
        "eventId": "GRB 260120B",
        "subject": "EP260119a: optical counterpart",
        "body": "Body mentions AT2025abc",
    }
    raw, events, source = extract_events(record)
    assert raw == "GRB 260120B"
    assert source == "eventId"
    assert "GRB260120B" in events


def test_extract_events_uses_subject_when_event_id_missing() -> None:
    record = {
        "eventId": None,
        "subject": "EP260119a: optical counterpart candidate",
        "body": "The source is a good candidate counterpart.",
    }
    _, events, source = extract_events(record)
    assert source == "subject"
    assert "EP260119A" in events


def test_extract_events_uses_subject_when_event_id_empty_string() -> None:
    record = {
        "eventId": "",
        "subject": "GRB 260120B: Swift detection",
        "body": "No other events mentioned.",
    }
    _, _, source = extract_events(record)
    assert source == "subject"


def test_extract_events_falls_through_to_body() -> None:
    record = {
        "eventId": None,
        "subject": "Optical follow-up observations",
        "body": "We observed the field of GRB 260120B and measured a fading source.",
    }
    _, events, source = extract_events(record)
    assert source == "body"
    assert "GRB260120B" in events


def test_extract_events_returns_none_when_no_event_found() -> None:
    record = {
        "eventId": None,
        "subject": "Optical observations",
        "body": "We observed the field and found no transient.",
    }
    raw, events, source = extract_events(record)
    assert raw is None
    assert events == []
    assert source == "none"


def test_extract_events_returns_multiple_body_events() -> None:
    record = {
        "eventId": None,
        "subject": "Follow-up report",
        "body": "We observed GRB 260120B and compared it with EP260119a.",
    }
    raw, events, source = extract_events(record)
    assert source == "body"
    assert "GRB260120B" in events
    assert "EP260119A" in events
    assert raw == "GRB260120B"


def test_extract_events_handles_all_none_fields() -> None:
    record: dict[str, None] = {"eventId": None, "subject": None, "body": None}
    raw, events, source = extract_events(record)
    assert raw is None
    assert events == []
    assert source == "none"


# ── extract_event_from_query ──────────────────────────────────────────────────


def test_extract_event_from_query_returns_first_event() -> None:
    query = "Find optical counterpart reports for EP260119a and compare with GRB 260120B"
    assert extract_event_from_query(query) == "EP260119A"


def test_extract_event_from_query_grb_in_query() -> None:
    assert extract_event_from_query("What happened with GRB 260120B?") == "GRB260120B"


def test_extract_event_from_query_returns_none_when_no_event() -> None:
    assert extract_event_from_query("Find redshift measurements and afterglow reports.") is None


def test_extract_event_from_query_empty_string() -> None:
    assert extract_event_from_query("") is None
