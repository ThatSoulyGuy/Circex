"""Poll gcn.nasa.gov for new circulars. Adapted from sjhend03/GCNMCP src/fetch_circulars.py.

The predecessor was a top-level script with hardcoded paths and print statements; we
expose proper functions here. Sprint 5 will wrap this in a daemon loop with the
indexer.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Final

import requests
import structlog

log = structlog.get_logger(__name__)

GCN_CIRCULAR_URL: Final[str] = "https://gcn.nasa.gov/circulars/{circular_id}.json"
DEFAULT_TIMEOUT: Final[float] = 10.0
DEFAULT_POLITE_DELAY: Final[float] = 0.2


def fetch_circular(circular_id: int, timeout: float = DEFAULT_TIMEOUT) -> str | None:
    """Fetch one circular by ID. Returns JSON text or None on 404."""
    url = GCN_CIRCULAR_URL.format(circular_id=circular_id)
    response = requests.get(url, timeout=timeout)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.text


def poll_range(
    out_dir: Path,
    start_id: int,
    max_id: int | None = None,
    delay: float = DEFAULT_POLITE_DELAY,
) -> int:
    """Poll circular IDs from start_id upward, writing each to {out_dir}/{id}.json.

    Stops on the first 404 (treated as end-of-archive) or when max_id is reached.
    Existing files are skipped. Returns the count of newly downloaded circulars.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    circular_id = start_id

    while True:
        if max_id is not None and circular_id > max_id:
            break

        out_path = out_dir / f"{circular_id}.json"
        if out_path.exists():
            circular_id += 1
            continue

        try:
            payload = fetch_circular(circular_id)
        except requests.RequestException as exc:
            log.warning("fetch_failed", circular_id=circular_id, error=str(exc))
            circular_id += 1
            continue

        if payload is None:
            log.info("end_of_archive", circular_id=circular_id)
            break

        out_path.write_text(payload, encoding="utf-8")
        downloaded += 1
        log.info("downloaded", circular_id=circular_id)
        time.sleep(delay)
        circular_id += 1

    return downloaded
