"""Event schema. Mirrors gcn-schema gcn/notices/core/Event.schema.json."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Event(BaseModel):
    """Name or names of the event."""

    event_name: str | list[str] | None = Field(
        default=None,
        description=(
            "Name of the event (ex: GRB 170817A), or array of names for the same event "
            "(ex: GRB 170817A, GW170817, AT2017gfo, SSS 17a)."
        ),
    )
    id: str | list[str] | None = Field(
        default=None,
        description=(
            "Instrument-specific trigger ID (ex: bn230313485 (Fermi), 1159327 (Swift)), "
            "or array of multiple IDs."
        ),
    )
    data_archive_page: str | None = Field(
        default=None,
        description="URL of archived data files.",
    )
