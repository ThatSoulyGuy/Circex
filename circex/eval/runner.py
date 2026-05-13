"""Eval runner — apply an extractor to a list of circulars with cost-cap enforcement."""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from circex.extract.protocol import Circular, Extractor
from circex.schema import CircularExtraction

log = structlog.get_logger(__name__)


@dataclass
class RunStats:
    n_total: int
    n_succeeded: int
    n_failed: int
    cost_usd: float
    aborted_for_cost: bool = False


def run_extractor(
    extractor: Extractor,
    circulars: list[Circular],
    max_usd: float | None = None,
) -> tuple[list[CircularExtraction], RunStats]:
    """Run an extractor sequentially over a list of circulars.

    If max_usd is set, halts cleanly when running cost would exceed the cap.
    Returns (successful extractions, stats).
    """
    out: list[CircularExtraction] = []
    cost = 0.0
    failed = 0
    aborted = False

    for circ in circulars:
        if max_usd is not None and cost >= max_usd:
            log.warning("cost_cap_hit", cost_usd=cost, max_usd=max_usd)
            aborted = True
            break
        try:
            result = extractor.extract(circ)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "extractor_failed",
                circular_id=circ.circular_id,
                extractor=getattr(extractor, "extractor_id", "?"),
                error=str(exc),
            )
            failed += 1
            continue
        out.append(result)
        if result.extraction_meta.cost_usd is not None:
            cost += result.extraction_meta.cost_usd

    return out, RunStats(
        n_total=len(circulars),
        n_succeeded=len(out),
        n_failed=failed,
        cost_usd=cost,
        aborted_for_cost=aborted,
    )
