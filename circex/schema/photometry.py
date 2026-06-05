"""Extended Photometry schema.

Base mirrors gcn-schema gcn/notices/core/Photometry.schema.json. Sprint 1 adds:
telescope, instrument, calibration_reference, galactic_extinction_corrected, seeing,
airmass; tightens mag_system to enum [AB, Vega, STMag] (BREAKING for the upstream PR).

These additions are the optical-specific extensions the plan calls for.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

MagSystem = Literal["AB", "Vega", "STMag"]
CalibrationReference = Literal["PS1", "SDSS", "APASS", "2MASS", "Gaia", "Other"]


class PhotometryExt(BaseModel):
    """Magnitude-based UV/optical/NIR photometry for one source in one filter (one row)."""

    filter: str | None = Field(
        default=None,
        description="Filter used for the observation (e.g., u, g, r, R, clear).",
    )
    bandpass: str | None = Field(
        default=None,
        description=(
            "Canonical bandpass name for downstream consumers (sncosmo/SkyPortal "
            "vocabulary), derived from `filter` + `mag_system` where possible. "
            "Sloan u/g/r/i/z -> sdss{u,g,r,i,z}; y -> ps1::y; "
            "Bessel U/B/V/R/I -> bessell{u,b,v,r,i}; "
            "NIR J/H/K/Ks -> 2mass{j,h,ks}. Null for unfiltered/clear or when the "
            "filter cannot be mapped (the raw `filter` string is always retained)."
        ),
    )
    mag: float | None = Field(
        default=None,
        description="Measured apparent magnitude [mag] of the source in the specified filter.",
    )
    mag_error: float | None = Field(
        default=None,
        description="1-sigma statistical uncertainty on magnitude [mag].",
    )
    mag_system: MagSystem | None = Field(
        default=None,
        description=(
            "Photometric magnitude system (zeropoint convention) for mag and limiting_mag. "
            "One of [AB, Vega, STMag]. Tightened from upstream open-string default."
        ),
    )
    limiting_mag: float | None = Field(
        default=None,
        description="Limiting magnitude (upper limit) for the observation [mag].",
    )
    limiting_mag_sigma: float | None = Field(
        default=None,
        description="Significance level [sigma] associated with limiting_mag (default 5).",
    )

    # ---- optical-specific extensions added by Circex ----
    telescope: str | None = Field(
        default=None, description="Name of the telescope (e.g., GTC, ZTF, Pan-STARRS1)."
    )
    instrument: str | None = Field(
        default=None, description="Name of the instrument (e.g., OSIRIS, ZTF Camera)."
    )
    calibration_reference: CalibrationReference | None = Field(
        default=None,
        description=(
            "Photometric calibration reference catalog. One of "
            "[PS1, SDSS, APASS, 2MASS, Gaia, Other]."
        ),
    )
    galactic_extinction_corrected: bool | None = Field(
        default=None,
        description="True if the reported magnitude has been corrected for Galactic extinction.",
    )
    seeing: float | None = Field(
        default=None,
        description="Seeing FWHM during the observation [arcsec].",
    )
    airmass: float | None = Field(
        default=None,
        description="Airmass during the observation [dimensionless].",
    )

    # ---- detection / non-detection flag ----
    is_detection: bool | None = Field(
        default=None,
        description=(
            "True if this row reports a measured magnitude; False if it reports only an "
            "upper limit (non-detection). Inferred automatically when not set explicitly: "
            "mag present ⇒ True, only limiting_mag present ⇒ False. When both are present "
            "(a detection plus the night's depth), this is True. When both are null the "
            "value is left null."
        ),
    )

    @model_validator(mode="after")
    def _infer_is_detection(self) -> PhotometryExt:
        """Auto-set is_detection when the caller leaves it null."""
        if self.is_detection is None:
            if self.mag is not None:
                self.is_detection = True
            elif self.limiting_mag is not None:
                self.is_detection = False
        return self
