"""Localization schema. Mirrors gcn-schema gcn/notices/core/Localization.schema.json."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Localization(BaseModel):
    """Localization of the transient — position + uncertainty region."""

    ra: float | None = Field(
        default=None,
        description=(
            "ICRS right ascension [deg], utilizes the J2000 epoch and an equatorial "
            "coordinate system."
        ),
    )
    dec: float | None = Field(
        default=None,
        description=(
            "ICRS declination [deg], utilizes the J2000 epoch and an equatorial "
            "coordinate system."
        ),
    )
    ra_dec_error: float | list[float] | None = Field(
        default=None,
        description=(
            "Uncertainty region as either a circle radius [deg] (number), or an ellipse "
            "as a 1-3 element array: semi-major axis, semi-minor axis (default = "
            "semi-major), position angle (default = 0, measured from North through East)."
        ),
    )
    containment_probability: float | None = Field(
        default=None,
        description="Containment probability [0-1]; if absent, default is 0.9.",
    )
    systematic_included: bool | None = Field(
        default=None,
        description=(
            "True when systematic error is included in ra_dec_error, false when it is not."
        ),
    )
    instrument_phi: float | None = Field(
        default=None, description="Instrument phi [deg]."
    )
    instrument_theta: float | None = Field(
        default=None, description="Instrument theta [deg]."
    )
    instrument_semimajor_angle: float | None = Field(
        default=None,
        description="Position angle of semi-major axis in instrument coordinates [deg].",
    )
    healpix_url: str | None = Field(
        default=None,
        description="URL of HEALPix localization probability file.",
    )
