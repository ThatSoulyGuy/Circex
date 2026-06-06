"""Classification — NEW schema for the optical extraction project.

Controlled vocabulary sourced from skyportal/timedomain-taxonomy (loaded via
circex.taxonomy). Validates that `classification` is a canonical class name from
the taxonomy. `subtype` is free-form (it often refines beyond the taxonomy's
hierarchical reach in a circular's prose).

Future upstream PR: nasa-gcn/gcn-schema.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from circex.taxonomy import canonical_classes, taxonomy_path


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
    taxonomy_path: list[str] | None = Field(
        default=None,
        description=(
            "Root-to-leaf hierarchy path for `classification` in the time-domain "
            "taxonomy (e.g., ['Time-domain Source', 'Stellar variable', "
            "'Cataclysmic', 'Supernova', 'Type I', 'Ia']). Auto-populated from "
            "`classification`; lets a downstream consumer collapse to a coarser "
            "campaign class without re-walking the taxonomy."
        ),
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

    @model_validator(mode="after")
    def _fill_taxonomy_path(self) -> Classification:
        """Always derive taxonomy_path from the canonical class.

        The path is a pure function of the (already-validated) canonical class,
        so we overwrite any supplied value — this prevents an LLM from injecting
        a hallucinated path, and round-trips are stable because reload re-derives
        the same value.
        """
        self.taxonomy_path = taxonomy_path(self.classification)
        return self
