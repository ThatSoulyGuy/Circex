"""Tests for the prompt template + few-shot rendering."""

from __future__ import annotations

from circex.extract.llm.prompt import (
    PROMPT_V1,
    build_messages,
    build_system_text,
    llm_input_schema,
)
from circex.extract.protocol import Circular


def test_prompt_version_is_iso_date() -> None:
    # Format: YYYY-MM-DD
    parts = PROMPT_V1.split("-")
    assert len(parts) == 3 and len(parts[0]) == 4


def test_system_text_contains_policy() -> None:
    text = build_system_text()
    assert "use null when not stated" in text.lower() or "null when" in text.lower()
    assert "icrs" in text.lower()
    assert "submit_extraction" in text


def test_build_messages_includes_few_shots_and_user() -> None:
    msgs = build_messages(Circular(circular_id=99, subject="S", body="Test body"))
    # 4 few-shots * 2 (user/assistant) + 1 final user = 9 messages.
    assert len(msgs) == 9
    assert msgs[-1]["role"] == "user"
    assert "Test body" in msgs[-1]["content"]


def test_few_shot_examples_are_alternating_user_assistant() -> None:
    msgs = build_messages(Circular(circular_id=1, subject="", body=""))
    # First 8 messages: u, a, u, a, u, a, u, a
    for i in range(0, 8, 2):
        assert msgs[i]["role"] == "user"
        assert msgs[i + 1]["role"] == "assistant"


def test_input_schema_excludes_extraction_meta() -> None:
    schema = llm_input_schema()
    assert "extraction_meta" not in schema.get("properties", {})
    assert "extraction_meta" not in schema.get("required", [])


def test_input_schema_keeps_event_and_photometry() -> None:
    schema = llm_input_schema()
    props = schema.get("properties", {})
    assert "event" in props
    assert "photometry" in props
