"""Tests for the JSON Schema dump."""

from __future__ import annotations

import json
import re
from pathlib import Path

from circex.schema.dump import (
    SCHEMA_VERSION,
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


def test_write_all_produces_three_schemas_plus_version(tmp_path: Path) -> None:
    written = write_all(tmp_path)
    assert {p.name for p in written} == {
        "Photometry.schema.json",
        "SpectralLines.schema.json",
        "Classification.schema.json",
        "VERSION",
    }
    for path in written:
        if path.name == "VERSION":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "$id" in payload
        assert "$schema" in payload


# ---- versioning (P2 #10) ----


def test_schema_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", SCHEMA_VERSION), SCHEMA_VERSION


def test_every_schema_carries_the_version() -> None:
    for dump in (dump_photometry, dump_spectral_lines, dump_classification):
        assert dump()["version"] == SCHEMA_VERSION


def test_version_file_matches_constant(tmp_path: Path) -> None:
    write_all(tmp_path)
    assert (tmp_path / "VERSION").read_text(encoding="utf-8").strip() == SCHEMA_VERSION
