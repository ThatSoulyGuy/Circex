"""Reporter schema. Mirrors gcn-schema gcn/notices/core/Reporter.schema.json."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Messenger = Literal["EM", "GW", "Neutrino"]
SpectralBandUnit = Literal["keV", "nm", "MHz"]


class Reporter(BaseModel):
    """Who issued the alert (the reporting instrument, not the photometry telescope)."""

    mission: str | None = Field(
        default=None,
        description="Name of mission or telescope reporting the event.",
    )
    instrument: str | None = Field(
        default=None,
        description="Name of the instrument reporting the event.",
    )
    record_number: int | None = Field(
        default=None,
        description="Incremental number for messages from the instrument during one trigger.",
    )
    messenger: Messenger | None = Field(
        default=None,
        description="Messenger of report: EM, GW, or Neutrino.",
    )
    spectral_band: list[float] | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="Observed spectral band [low, high] in the specified spectral_band_units.",
    )
    spectral_band_units: SpectralBandUnit | None = Field(
        default=None,
        description="Units for spectral_band (keV, nm, MHz). Default keV.",
    )
