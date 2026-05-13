"""OllamaExtractor tests with mocked ollama client (no live daemon)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from circex.extract.llm.ollama import OllamaExtractor
from circex.extract.protocol import Circular


def _mock_ollama(*responses: dict[str, object]) -> MagicMock:
    """Return a MagicMock whose .chat returns each given response in turn."""
    client = MagicMock()
    client.chat.side_effect = [
        {"message": {"content": json.dumps(r)}} for r in responses
    ]
    return client


def test_extractor_id() -> None:
    ext = OllamaExtractor(client=_mock_ollama({}))
    assert ext.extractor_id == "ollama:mistral:7b-instruct-v0.2"


def test_extract_basic_success() -> None:
    client = _mock_ollama({"event": {"event_name": "GRB 240101A"}, "photometry": []})
    ext = OllamaExtractor(client=client)
    result = ext.extract(Circular(circular_id=7, subject="", body="body"))
    assert result.circular_id == 7
    assert result.event is not None and result.event.event_name == "GRB 240101A"
    assert client.chat.call_count == 1


def test_extract_repairs_on_validation_error() -> None:
    """First response invalid (bogus classification); repair retry returns valid."""
    bad = {"classification": {"classification": "DefinitelyNotARealClass"}}
    good = {"event": {"event_name": "GRB X"}}
    client = _mock_ollama(bad, good)
    ext = OllamaExtractor(client=client)
    result = ext.extract(Circular(circular_id=1, subject="", body="b"))
    assert client.chat.call_count == 2
    assert result.event is not None


def test_meta_populated_without_cost() -> None:
    client = _mock_ollama({})
    ext = OllamaExtractor(client=client)
    result = ext.extract(Circular(circular_id=1, subject="", body=""))
    assert result.extraction_meta.cost_usd is None
    assert result.extraction_meta.latency_ms is not None
