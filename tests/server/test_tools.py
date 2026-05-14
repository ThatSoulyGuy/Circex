"""Tests for the 7 MCP tool implementations (server-side)."""

from __future__ import annotations

from pathlib import Path

import pytest

from circex.schema import (
    CircularExtraction,
    Classification,
    Event,
    ExtractionMeta,
    PhotometryExt,
    Redshift,
)
from circex.server.registry import ToolContext, dispatch
from circex.server.store import ExtractionStore


def _full_extraction(circular_id: int, event: str) -> CircularExtraction:
    return CircularExtraction(
        circular_id=circular_id,
        event=Event(event_name=event),
        redshift=Redshift(redshift=0.215, redshift_type="host"),
        classification=Classification(classification="Ic-BL"),
        photometry=[PhotometryExt(filter="r", mag=18.5, mag_system="AB")],
        extraction_meta=ExtractionMeta(extractor="regex-v1"),
    )


@pytest.fixture
def populated_ctx(tmp_path: Path) -> ToolContext:
    store = ExtractionStore(tmp_path / "s.sqlite")
    store.put(_full_extraction(1, "GRB 240101A"))
    store.put(_full_extraction(2, "GRB 240202B"))
    return ToolContext(store=store)


def test_get_redshift_returns_first_match(populated_ctx: ToolContext) -> None:
    result = dispatch(populated_ctx, "get_redshift", {"event": "GRB 240101A"})
    assert result is not None
    assert result["redshift"] == 0.215


def test_get_redshift_unknown_event_returns_none(populated_ctx: ToolContext) -> None:
    assert dispatch(populated_ctx, "get_redshift", {"event": "GRB XYZ"}) is None


def test_get_photometry_returns_all_rows(populated_ctx: ToolContext) -> None:
    rows = dispatch(populated_ctx, "get_photometry", {"event": "GRB 240101A"})
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert rows[0]["filter"] == "r"
    assert rows[0]["mag"] == 18.5


def test_get_classification_returns_canonical(populated_ctx: ToolContext) -> None:
    result = dispatch(populated_ctx, "get_classification", {"event": "GRB 240101A"})
    assert result is not None
    assert result["classification"] == "Ic-BL"


def test_get_redshift_missing_event_arg_errors(populated_ctx: ToolContext) -> None:
    with pytest.raises(ValueError, match="event"):
        dispatch(populated_ctx, "get_redshift", {})


def test_extract_properties_without_default_extractor_errors(
    populated_ctx: ToolContext,
) -> None:
    """No default_extractor in ctx; missing circular_id 999."""
    with pytest.raises(ValueError, match="no default extractor"):
        dispatch(populated_ctx, "extract_properties", {"circular_id": 999})


def test_extract_properties_serves_from_store_when_cached(
    populated_ctx: ToolContext,
) -> None:
    """Stored extractions returned without re-extracting (no extractor in ctx)."""

    class _StubExtractor:
        extractor_id = "regex-v1"
        model_id = ""
        prompt_version = ""

        def extract(self, _: object) -> CircularExtraction:
            raise AssertionError("should not be called when cached")

    populated_ctx.default_extractor = _StubExtractor()
    result = dispatch(populated_ctx, "extract_properties", {"circular_id": 1})
    assert result["circular_id"] == 1
    assert result["event"]["event_name"] == "GRB 240101A"
