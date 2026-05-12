"""ExtractionMeta — provenance and cost metadata for one extraction run.

Attached to every CircularExtraction so that eval, cost projection, and cache
invalidation work cleanly. Not part of the upstream gcn-schema PR — this is
Circex-internal.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractionMeta(BaseModel):
    """Metadata for one extractor run on one circular."""

    extractor: str = Field(
        description=(
            "Extractor identifier "
            "(e.g., 'regex-v1', 'claude-haiku-4-5', 'ollama-mistral-7b')."
        ),
    )
    model_id: str | None = Field(
        default=None,
        description="Provider model ID, if applicable (e.g., 'claude-haiku-4-5-20251001').",
    )
    prompt_version: str | None = Field(
        default=None,
        description="Prompt version string (e.g., 'PROMPT_V1'). None for regex extractor.",
    )
    tokens_in: int | None = Field(
        default=None, description="Prompt tokens billed."
    )
    tokens_out: int | None = Field(
        default=None, description="Completion tokens billed."
    )
    latency_ms: float | None = Field(
        default=None, description="Wall-clock latency for this extraction [ms]."
    )
    cost_usd: float | None = Field(
        default=None, description="Computed cost for this extraction [USD]."
    )
    cache_hit: bool = Field(
        default=False, description="True if served from the local LLM cache."
    )
