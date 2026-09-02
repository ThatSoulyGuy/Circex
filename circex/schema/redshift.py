"""Redshift schema. Mirrors gcn-schema gcn/notices/core/Redshift.schema.json."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RedshiftMeasure = Literal["spectroscopic", "photometric"]
RedshiftType = Literal["emission", "absorption", "host"]


class Redshift(BaseModel):
    """Redshift measure of the transient."""

    redshift: float | None = Field(
        default=None,
        description="Redshift z — displacement of spectral lines toward longer wavelengths.",
    )
    redshift_error: float | list[float] | None = Field(
        default=None,
        description=(
            "Statistical error in redshift. Number for symmetric, 2-element array for asymmetric."
        ),
    )
    redshift_measure: RedshiftMeasure | None = Field(
        default=None,
        description="Measurement method: spectroscopic or photometric.",
    )
    redshift_type: RedshiftType | None = Field(
        default=None,
        description="Spectral feature type: emission, absorption, or host.",
    )
