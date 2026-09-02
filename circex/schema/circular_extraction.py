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
from circex.schema.span import Span
from circex.schema.spectral_lines import SpectralLines
from circex.schema.time_offset import TimeOffset


class CircularExtraction(BaseModel):
    """Structured extraction from one GCN circular.

    The optional `provenance` field maps dotted field paths to character-offset
    spans into `Circular.body`. The convention is:

    - Object-level keys for nested singletons: ``"event"``, ``"redshift"``,
      ``"localization"``, ``"classification"``, ``"follow_up"``, ``"datetime"``.
    - Indexed keys for list items: ``"photometry[0]"``, ``"time_offsets[2]"``.
    - Leaf-level keys are also permitted, allowing finer attribution when an
      extractor can support it: ``"redshift.redshift"``, ``"localization.ra"``,
      ``"photometry[0].mag"``. The regex baseline emits object-level keys; the
      LLM extractors are prompted to emit leaf-level keys where they can.

    `provenance` is operationally distinct from `extraction_meta`: the former
    describes the *data* (where a value came from in the source text); the
    latter describes the *run* (which extractor, what model, how much it cost).
    Downstream consumers can ignore `provenance` entirely without loss of value.
    """

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
            "One PhotometryExt per (filter, epoch) row. Multi-epoch tables become multiple rows."
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

    retraction: bool = Field(
        default=False,
        description=(
            "True when the circular withdraws a previously reported trigger. Such a "
            "circular still names the event and may restate its position; consumers "
            "should not treat those values as a new detection."
        ),
    )

    provenance: dict[str, Span] = Field(
        default_factory=dict,
        description=(
            "Per-field pointers back into Circular.body, keyed by dotted field "
            "path. Object-level keys (e.g., 'redshift', 'photometry[0]') are the "
            "v1 convention; leaf-level keys (e.g., 'redshift.redshift') are "
            "permitted. Empty by default; extractors populate what they can."
        ),
    )

    extraction_meta: ExtractionMeta = Field(
        description="Extraction run metadata: model, prompt version, tokens, cost, latency."
    )

    model_config = {"populate_by_name": True}
