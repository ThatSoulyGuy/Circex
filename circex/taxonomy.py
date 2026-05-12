"""Time-domain taxonomy loader.

Reads YAML files directly from `references/timedomain-taxonomy/tdtax/` (the local
clone of skyportal/timedomain-taxonomy). We bypass the `tdtax` PyPI package because
its setup.py fails on Python 3.14 (uses removed `ast.Constant.s`).

Loads lazily on first access. The merged taxonomy, the set of canonical class names,
and the alias->canonical map are all cached in module-level state after the first
load.

The YAML structure (per node):

    class: <canonical name>             # required
    tags: [...]                         # optional
    other names: [<alias1>, <alias2>]   # optional aliases
    subclasses:                         # optional children
      - class: ...
      - ref: somefile.yaml              # load and inline another file
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any, cast

import yaml

from circex.config import get_settings


def _merge_yamls(top_path: Path) -> dict[str, Any]:
    """Load top.yaml and recursively inline any `ref:` references."""
    base_dir = top_path.parent
    with top_path.open("r", encoding="utf-8") as f:
        taxonomy = cast(dict[str, Any], yaml.safe_load(f))
    _resolve_refs(taxonomy, base_dir)
    return taxonomy


def _resolve_refs(node: Any, base_dir: Path) -> None:
    """Walk a node in-place, replacing `{ref: filename.yaml}` entries with their content."""
    if isinstance(node, dict):
        for value in node.values():
            _resolve_refs(value, base_dir)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            if isinstance(item, dict) and "ref" in item:
                ref_path = base_dir / item["ref"]
                if ref_path.exists():
                    with ref_path.open("r", encoding="utf-8") as f:
                        node[i] = cast(dict[str, Any], yaml.safe_load(f))
                else:
                    node[i] = {"class": ref_path.stem + "-placeholder"}
            _resolve_refs(node[i], base_dir)


def _walk_classes(node: Any, out: list[tuple[str, list[str]]]) -> None:
    """Walk merged taxonomy. Append (class_name, [other_names]) for every node."""
    if isinstance(node, dict):
        if "class" in node and isinstance(node["class"], str):
            aliases = node.get("other names") or []
            if not isinstance(aliases, list):
                aliases = []
            out.append((node["class"], [str(a) for a in aliases]))
        for value in node.values():
            _walk_classes(value, out)
    elif isinstance(node, list):
        for item in node:
            _walk_classes(item, out)


@cache
def get_taxonomy() -> dict[str, Any]:
    """Return the merged taxonomy tree as a dict."""
    top = get_settings().taxonomy_dir / "top.yaml"
    if not top.exists():
        raise FileNotFoundError(
            f"Taxonomy top.yaml not found at {top}. Set CIRCEX_TAXONOMY_DIR or clone "
            f"skyportal/timedomain-taxonomy into references/."
        )
    return _merge_yamls(top)


@cache
def canonical_classes() -> frozenset[str]:
    """Return the frozen set of all canonical class names from the taxonomy."""
    pairs: list[tuple[str, list[str]]] = []
    _walk_classes(get_taxonomy(), pairs)
    return frozenset(canonical for canonical, _ in pairs)


@cache
def alias_to_canonical() -> dict[str, str]:
    """Return a lowercased-alias -> canonical-class map.

    Each canonical class also maps to itself (canonical lookups are case-insensitive).
    On alias collisions, the first-seen wins.
    """
    pairs: list[tuple[str, list[str]]] = []
    _walk_classes(get_taxonomy(), pairs)
    mapping: dict[str, str] = {}
    for canonical, aliases in pairs:
        # Canonical name maps to itself.
        mapping.setdefault(canonical.lower(), canonical)
        for alias in aliases:
            mapping.setdefault(alias.lower(), canonical)
    return mapping


def normalize_classification(text: str) -> str | None:
    """Look up text in the alias map. Returns the canonical class or None.

    Match is case-insensitive on the whole input. Use the regex classification
    extractor for substring matching in body text — this is a strict lookup.
    """
    return alias_to_canonical().get(text.strip().lower())
