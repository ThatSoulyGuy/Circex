"""Tests for the ExtractionStore."""

from __future__ import annotations

from pathlib import Path

from circex.schema import CircularExtraction, Event, ExtractionMeta, Redshift
from circex.server.store import ExtractionStore


def _make_extraction(
    circular_id: int = 1,
    event_name: str | None = "GRB 240101A",
    redshift: float | None = None,
    extractor: str = "regex-v1",
    prompt_version: str = "",
) -> CircularExtraction:
    return CircularExtraction(
        circular_id=circular_id,
        event=Event(event_name=event_name) if event_name else None,
        redshift=Redshift(redshift=redshift) if redshift is not None else None,
        extraction_meta=ExtractionMeta(extractor=extractor, prompt_version=prompt_version),
    )


def test_put_get_roundtrip(tmp_path: Path) -> None:
    with ExtractionStore(tmp_path / "s.sqlite") as store:
        ex = _make_extraction(circular_id=42, redshift=0.5)
        store.put(ex)
        got = store.get(circular_id=42, extractor_id="regex-v1")
        assert got is not None
        assert got.circular_id == 42
        assert got.redshift is not None
        assert got.redshift.redshift == 0.5


def test_put_replaces_same_key(tmp_path: Path) -> None:
    with ExtractionStore(tmp_path / "s.sqlite") as store:
        store.put(_make_extraction(redshift=0.5))
        store.put(_make_extraction(redshift=0.8))  # same composite key
        got = store.get(circular_id=1, extractor_id="regex-v1")
        assert got is not None
        assert got.redshift is not None and got.redshift.redshift == 0.8
        assert store.count() == 1


def test_different_extractors_coexist(tmp_path: Path) -> None:
    with ExtractionStore(tmp_path / "s.sqlite") as store:
        store.put(_make_extraction(extractor="regex-v1"))
        store.put(_make_extraction(extractor="claude:claude-haiku-4-5"))
        assert store.count() == 2


def test_find_by_event_returns_matching(tmp_path: Path) -> None:
    with ExtractionStore(tmp_path / "s.sqlite") as store:
        store.put(_make_extraction(circular_id=1, event_name="GRB 240101A"))
        store.put(_make_extraction(circular_id=2, event_name="GRB 240101A"))
        store.put(_make_extraction(circular_id=3, event_name="GRB 240202B"))
        matches = list(store.find_by_event("GRB 240101A"))
        assert len(matches) == 2
        assert {m.circular_id for m in matches} == {1, 2}


def test_find_by_event_filters_by_extractor(tmp_path: Path) -> None:
    with ExtractionStore(tmp_path / "s.sqlite") as store:
        store.put(_make_extraction(circular_id=1, extractor="regex-v1"))
        store.put(_make_extraction(circular_id=2, extractor="claude:M"))
        regex_only = list(store.find_by_event("GRB 240101A", extractor_id="regex-v1"))
        assert len(regex_only) == 1
        assert regex_only[0].circular_id == 1


def test_event_name_list_uses_first(tmp_path: Path) -> None:
    with ExtractionStore(tmp_path / "s.sqlite") as store:
        ex = CircularExtraction(
            circular_id=99,
            event=Event(event_name=["GW170817", "AT2017gfo"]),
            extraction_meta=ExtractionMeta(extractor="test"),
        )
        store.put(ex)
        assert list(store.find_by_event("GW170817"))
        # The second name isn't indexed (only first is); document this.
        assert not list(store.find_by_event("AT2017gfo"))


def test_list_circular_ids_distinct(tmp_path: Path) -> None:
    with ExtractionStore(tmp_path / "s.sqlite") as store:
        store.put(_make_extraction(circular_id=1, extractor="regex-v1"))
        store.put(_make_extraction(circular_id=1, extractor="claude:M"))
        store.put(_make_extraction(circular_id=2, extractor="regex-v1"))
        assert store.list_circular_ids() == [1, 2]
