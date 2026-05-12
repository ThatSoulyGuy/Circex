"""TimeOffset — captures literal t-since-trigger phrasings as-is.

Per PDF decision 4: extract literal time offsets ("observations began T+234s") with
units, do NOT resolve them against the absolute trigger time T0 in v1.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TimeOffsetUnit = Literal["s", "m", "h", "d"]


class TimeOffset(BaseModel):
    """A relative time offset extracted literally from a circular."""

    value: float = Field(description="Numeric value of the offset.")
    unit: TimeOffsetUnit = Field(description="Time unit: s, m, h, or d.")
    reference: str = Field(
        description=(
            "What the offset is relative to, as written in the circular. "
            "Examples: 'T+', 'T-', 'trigger', 'GW alert'."
        ),
    )
