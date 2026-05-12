"""DateTime schema. Mirrors gcn-schema gcn/notices/core/DateTime.schema.json.

Module is named `datetime_` to avoid clashing with the stdlib `datetime` module
in import resolution; the class itself is exported as ``DateTime`` from
``circex.schema``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DateTime(BaseModel):
    """Time descriptions of transient event and observation."""

    trigger_time: str | None = Field(
        default=None,
        description="Time of the trigger [ISO 8601], ex YYYY-MM-DDTHH:MM:SS.ssssssZ.",
    )
    trigger_time_error: float | list[float] | None = Field(
        default=None,
        description=(
            "Trigger time uncertainty [s, 1-sigma]. Number for symmetric uncertainty, "
            "or 2-element array for asymmetric."
        ),
    )
    observation_start: str | None = Field(
        default=None,
        description="Start time of the observation [ISO 8601].",
    )
    observation_stop: str | None = Field(
        default=None,
        description="Stop time of the observation [ISO 8601].",
    )
    observation_livetime: float | None = Field(
        default=None,
        description="Livetime of the observation [s].",
    )
