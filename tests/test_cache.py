"""Tests for the SQLite LLM cache."""

from __future__ import annotations

from pathlib import Path

from circex.cache.llm import LLMCache, cache_key
from circex.schema import CircularExtraction, ExtractionMeta


def _ext(circular_id: int = 1, extractor: str = "claude:claude-haiku-4-5") -> CircularExtraction:
    return CircularExtraction(
        circular_id=circular_id,
        extraction_meta=ExtractionMeta(extractor=extractor, prompt_version="2026-05-13"),
    )


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    with LLMCache(tmp_path / "c.sqlite") as cache:
        assert cache.get("E", "M", "V", 1, "abc") is None


def test_cache_roundtrip(tmp_path: Path) -> None:
    with LLMCache(tmp_path / "c.sqlite") as cache:
        cache.put(
            extractor_id="claude:M",
            model_id="M",
            prompt_version="V1",
            circular_id=7,
            body_sha1="abc",
            extraction=_ext(circular_id=7),
            tokens_in=100,
            tokens_out=50,
            cost_usd=0.001,
            latency_ms=850.0,
        )
        cached = cache.get("claude:M", "M", "V1", 7, "abc")
        assert cached is not None
        assert cached.tokens_in == 100
        assert cached.cost_usd == 0.001
        assert cached.extraction.circular_id == 7


def test_cache_key_components_differentiate_versions(tmp_path: Path) -> None:
    """A different prompt_version must miss the cache."""
    with LLMCache(tmp_path / "c.sqlite") as cache:
        cache.put("E", "M", "V1", 1, "abc", _ext())
        assert cache.get("E", "M", "V1", 1, "abc") is not None
        assert cache.get("E", "M", "V2", 1, "abc") is None
        assert cache.get("E", "M", "V1", 1, "xyz") is None


def test_cache_replaces_existing_entry(tmp_path: Path) -> None:
    with LLMCache(tmp_path / "c.sqlite") as cache:
        cache.put("E", "M", "V", 1, "abc", _ext())
        cache.put("E", "M", "V", 1, "abc", _ext(), tokens_in=999)
        cached = cache.get("E", "M", "V", 1, "abc")
        assert cached is not None
        assert cached.tokens_in == 999


def test_cache_key_is_sha1_hex() -> None:
    h = cache_key("hello")
    assert len(h) == 40
    assert all(c in "0123456789abcdef" for c in h)
