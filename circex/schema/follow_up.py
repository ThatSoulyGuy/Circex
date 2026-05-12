"""FollowUp schema. Mirrors gcn-schema gcn/notices/core/FollowUp.schema.json."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FollowUp(BaseModel):
    """Schema specific to follow-up cases (e.g., optical counterpart to GW/neutrino)."""

    ref_type: str | None = Field(
        default=None,
        description="Type of the event detected, ex. GRB, GW, neutrino.",
    )
    ref_instrument: str | None = Field(
        default=None,
        description="Name of the reference mission or instrument, ex. Fermi-GBM.",
    )
    ref_ID: str | None = Field(
        default=None,
        description="Trigger ID as reported by the reference instrument, ex. bnYYMMDDFF.",
    )
    reference: dict[str, str | float] | None = Field(
        default=None,
        description=(
            "Reference as distributed by the notices or circulars or ATel, "
            "ex. {gcn_circulars: 12345}."
        ),
    )
