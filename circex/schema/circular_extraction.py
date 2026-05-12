"""CircularExtraction — top-level model for one circular's structured contribution.

This is the LLM and regex extractor output schema, and also the eval input shape.
Mirrors the union of all sub-schemas plus extraction provenance.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from circex.schema.classification import Classification
from circex.schema.datetime_ import DateTime
from circex.schema.event import Event
from circex.schema.extraction_meta import ExtractionMeta
from circex.schema.follow_up import FollowUp
from circex.schema.localization import Localization
from circex.schema.photometry import PhotometryExt
from circex.schema.redshift import Redshift
from circex.schema.reporter import Reporter
from circex.schema.spectral_lines import SpectralLines
from circex.schema.time_offset import TimeOffset


class CircularExtraction(BaseModel):
    """Structured extraction from one GCN circular."""

    circular_id: int = Field(description="Integer GCN circular ID.")

    event: Event | None = Field(default=None, description="Event identification.")
    follow_up: FollowUp | None = Field(
        default=None,
        description="Cross-references / counterpart-of relations to another event.",
    )
    localization: Localization | None = Field(
        default=None, description="Position and uncertainty region."
    )
    datetime_: DateTime | None = Field(
        default=None,
        alias="datetime",
        description="Trigger and observation times (absolute).",
    )
    time_offsets: list[TimeOffset] = Field(
        default_factory=list,
        description="Literal T+offset captures from the circular's prose (no T0 resolution).",
    )
    photometry: list[PhotometryExt] = Field(
        default_factory=list,
        description=(
            "One PhotometryExt per (filter, epoch) row. Multi-epoch tables become "
            "multiple rows."
        ),
    )
    spectroscopy: SpectralLines | None = Field(
        default=None, description="Identified spectral lines, if reported."
    )
    classification: Classification | None = Field(
        default=None, description="Source classification from controlled vocabulary."
    )
    redshift: Redshift | None = Field(default=None, description="Redshift measurement.")
    reporter: Reporter | None = Field(
        default=None,
        description="Who issued the alert (do NOT conflate with photometry.telescope).",
    )

    extraction_meta: ExtractionMeta = Field(
        description="Extraction provenance: model, prompt version, tokens, cost, latency."
    )

    model_config = {"populate_by_name": True}
