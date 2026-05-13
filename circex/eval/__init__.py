"""Four-way evaluation harness (regex / Claude-Haiku / Claude-Sonnet / Ollama / Vidushi)."""

from circex.eval.metrics import (
    FIELD_TOLERANCES,
    Comparison,
    FieldMetrics,
    compare_extractions,
    compute_field_metrics,
)
from circex.eval.runner import run_extractor
from circex.eval.vidushi_adapter import (
    SwiftEvaluationRow,
    load_vidushi_eval,
    vidushi_gold_extraction,
    vidushi_predicted_extraction,
)

__all__ = [
    "Comparison",
    "FIELD_TOLERANCES",
    "FieldMetrics",
    "SwiftEvaluationRow",
    "compare_extractions",
    "compute_field_metrics",
    "load_vidushi_eval",
    "run_extractor",
    "vidushi_gold_extraction",
    "vidushi_predicted_extraction",
]
