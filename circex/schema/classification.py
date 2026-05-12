"""Classification — NEW schema for the optical extraction project.

Controlled vocabulary sourced from skyportal/timedomain-taxonomy (loaded via
circex.taxonomy). Validates that `classification` is a canonical class name from
the taxonomy. `subtype` is free-form (it often refines beyond the taxonomy's
hierarchical reach in a circular's prose).

Future upstream PR: nasa-gcn/gcn-schema.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from circex.taxonomy import canonical_classes


class Classification(BaseModel):
    """Source classification with optional subtype and confidence."""

    classification: str = Field(
        description=(
            "Canonical class name from skyportal/timedomain-taxonomy "
            "(e.g., 'Ia', 'Ic-BL', 'Tidal Disruption Event', 'kilonova')."
        ),
    )
    subtype: str | None = Field(
        default=None,
        description="Free-form subtype refinement when the taxonomy lacks a finer class.",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Classifier confidence [0-1] when reported.",
    )

    @field_validator("classification")
    @classmethod
    def _validate_against_taxonomy(cls, v: str) -> str:
        valid = canonical_classes()
        if v not in valid:
            raise ValueError(
                f"classification {v!r} is not a canonical class in the time-domain "
                f"taxonomy. Use circex.taxonomy.normalize_classification() to map "
                f"aliases to canonical names before constructing this model."
            )
        return v
