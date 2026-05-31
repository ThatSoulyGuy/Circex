"""Span — character-offset pointer back into a circular's body text.

Used by every extractor to record *where* a value came from, not just *what* it
is. Aggregated into CircularExtraction.provenance, keyed by dotted field path
(e.g., "redshift", "photometry[0]", "localization"). Object-level keys are the
v1 convention; leaf-level keys ("redshift.redshift", "localization.ra") are
permitted by the schema and used by the LLM extractors where they can attribute
more precisely.

`snippet` is the literal body[start:end] substring, stored for round-trip
verification (a downstream consumer that re-fetches the circular can confirm
the offsets still resolve to the same text).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Span(BaseModel):
    """Character-range pointer into a circular's body text."""

    start: int = Field(ge=0, description="Inclusive character offset into circular.body.")
    end: int = Field(ge=0, description="Exclusive character offset into circular.body.")
    snippet: str = Field(
        description=(
            "Literal body[start:end] substring at extraction time. Stored for "
            "round-trip verification by downstream consumers."
        ),
    )
