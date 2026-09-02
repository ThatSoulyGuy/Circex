"""Untar the Sharma et al. 2025 GCN circulars archive and iterate over records.

Source: references/circulars-nlp-paper/data/archive_2025.json.tar.gz (~27 MB, ~40,506
circulars; one JSON file per circular). Untarred on first call into
{data_dir}/archive_2025/ with a sentinel file to avoid re-extracting.

Each circular file has fields: subject, eventId, bibcode, createdOn, circularId,
submitter, email, body.
"""

from __future__ import annotations

import json
import tarfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import structlog

from circex.config import get_settings

log = structlog.get_logger(__name__)

DEFAULT_TARBALL = Path("references/circulars-nlp-paper/data/archive_2025.json.tar.gz")
ARCHIVE_DIRNAME = "archive_2025"
SENTINEL_FILENAME = ".circex_archive_extracted"


def archive_dir() -> Path:
    """Directory where the archive is (or will be) extracted."""
    return get_settings().data_dir / ARCHIVE_DIRNAME


def untar_archive(tarball: Path = DEFAULT_TARBALL, force: bool = False) -> Path:
    """Untar the archive into {data_dir}/archive_2025/. Idempotent.

    Returns the extraction directory. Raises FileNotFoundError if the tarball
    is missing.
    """
    out_dir = archive_dir()
    sentinel = out_dir / SENTINEL_FILENAME

    if sentinel.exists() and not force:
        log.info("archive_already_extracted", out_dir=str(out_dir))
        return out_dir

    if not tarball.exists():
        raise FileNotFoundError(
            f"Archive tarball not found at {tarball}. Clone "
            f"nasa-gcn/circulars-nlp-paper into references/."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    log.info("extracting_archive", tarball=str(tarball), out_dir=str(out_dir))

    with tarfile.open(tarball, "r:gz") as tf:
        tf.extractall(out_dir, filter="data")

    sentinel.write_text("ok\n", encoding="utf-8")
    log.info("archive_extracted", out_dir=str(out_dir))
    return out_dir


def _find_json_root(out_dir: Path) -> Path:
    """The tarball may extract into a nested subdir; find the dir with circular JSONs.

    Filename collisions with directories matter here: this tarball nests circulars in
    a subdir literally named ``archive.json/``, so we must check ``is_file()`` when
    looking for JSON files at each level.
    """
    if any(p.is_file() for p in out_dir.glob("*.json")):
        return out_dir
    for child in out_dir.iterdir():
        if child.is_dir() and any(p.is_file() for p in child.glob("*.json")):
            return child
    raise FileNotFoundError(f"No *.json files found under {out_dir} after extraction.")


def iter_circulars(
    out_dir: Path | None = None,
    circular_ids: Iterable[int] | None = None,
) -> Iterable[dict[str, Any]]:
    """Yield circular records from the extracted archive.

    If `circular_ids` is given, only those records are yielded (filename-based lookup,
    not full directory walk).
    """
    base = out_dir or archive_dir()
    json_root = _find_json_root(base)

    if circular_ids is not None:
        for cid in circular_ids:
            path = json_root / f"{cid}.json"
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as f:
                yield json.load(f)
        return

    for child in sorted(json_root.glob("*.json")):
        with child.open("r", encoding="utf-8") as f:
            yield json.load(f)
