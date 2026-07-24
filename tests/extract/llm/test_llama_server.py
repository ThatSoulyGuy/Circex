"""Tests for the llama.cpp-server extractor (grammar-constrained JSON)."""

from __future__ import annotations

import json
from pathlib import Path

import requests

from circex.cache.llm import LLMCache
from circex.extract.llm import LlamaServerExtractor
from circex.extract.protocol import Circular


class _FakeResp:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}


class _FakeSession:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[tuple[str, dict]] = []

    def post(self, url: str, json: dict, timeout: float) -> _FakeResp:  # noqa: A002
        self.calls.append((url, json))
        return _FakeResp(self.content)


def test_llama_server_parses_grammar_constrained_output() -> None:
    model_output = json.dumps(
        {"event": {"event_name": "GRB 260604C"}, "redshift": {"redshift": 0.5}, "provenance": {}}
    )
    session = _FakeSession(model_output)
    ext = LlamaServerExtractor(base_url="http://agc03:8080", session=session)
    result = ext.extract(Circular(circular_id=44877, subject="", body="GRB 260604C at z = 0.5"))

    assert result.circular_id == 44877
    assert result.event is not None and result.event.event_name == "GRB 260604C"
    assert result.redshift is not None and result.redshift.redshift == 0.5
    assert result.extraction_meta.extractor == "llama-server:mistral-7b"


def test_llama_server_uses_grammar_constrained_request() -> None:
    session = _FakeSession(json.dumps({"provenance": {}}))
    LlamaServerExtractor(session=session).extract(Circular(circular_id=1, subject="", body="x"))
    url, payload = session.calls[0]
    assert url.endswith("/v1/chat/completions")
    assert payload["temperature"] == 0
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["schema"]["type"] == "object"
    json.dumps(payload)  # messages must be JSON-serializable for the real POST


class _FailSession:
    """Session whose POST always dies mid-flight, like a dropped tunnel."""

    def post(self, url: str, json: dict, timeout: float) -> _FakeResp:  # noqa: A002
        raise requests.ConnectionError("('Connection aborted.', ConnectionResetError(54, ...))")


def test_llama_server_does_not_cache_on_transport_failure(tmp_path: Path) -> None:
    # A transport error must fail soft (no crash) AND leave the cache empty, so a
    # re-run re-hits the model instead of returning a poisoned empty extraction.
    cache = LLMCache(tmp_path / "llm.sqlite")
    ext = LlamaServerExtractor(cache=cache, session=_FailSession())
    result = ext.extract(Circular(circular_id=6418, subject="", body="GRB 260604C at z = 0.5"))

    assert result.circular_id == 6418  # fail-soft: returns an (empty) extraction
    assert cache.count() == 0  # but nothing was persisted


def test_llama_server_binds_body_observation_epoch_to_untimed_rows() -> None:
    """A table row with no date column gets obs_mjd from a single body-level
    observation time, matching the regex extractor (GCN 45198 regression)."""
    model_output = json.dumps(
        {"event": {"event_name": "AT2026vts"}, "photometry": [{"filter": "r", "mag": 19.78}]}
    )
    body = "We began observations at 2026-07-23 04:54 UTC and measured the candidate."
    ext = LlamaServerExtractor(session=_FakeSession(model_output))
    result = ext.extract(Circular(circular_id=45198, subject="", body=body))
    assert result.photometry[0].obs_mjd is not None
    assert result.photometry[0].obs_time is not None
