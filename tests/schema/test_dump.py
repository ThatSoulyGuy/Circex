"""Tests for the JSON Schema dump."""

from __future__ import annotations

import json
from pathlib import Path

from circex.schema.dump import (
    dump_classification,
    dump_photometry,
    dump_spectral_lines,
    write_all,
)


def test_photometry_has_gcn_id() -> None:
    schema = dump_photometry()
    assert schema["$id"].endswith("/Photometry.schema.json")
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["title"].startswith("Photometry")


def test_spectral_lines_is_array_type() -> None:
    schema = dump_spectral_lines()
    assert schema["type"] == "array"
    assert "items" in schema


def test_classification_dump_has_taxonomy_constraint() -> None:
    schema = dump_classification()
    # The classification property exists and is required.
    assert "classification" in schema["properties"]
    assert "classification" in schema.get("required", [])


def test_write_all_produces_three_files(tmp_path: Path) -> None:
    written = write_all(tmp_path)
    assert {p.name for p in written} == {
        "Photometry.schema.json",
        "SpectralLines.schema.json",
        "Classification.schema.json",
    }
    for path in written:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "$id" in payload
        assert "$schema" in payload
