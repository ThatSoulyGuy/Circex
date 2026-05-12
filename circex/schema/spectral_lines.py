"""SpectralLines — NEW schema for the optical extraction project.

Sits alongside the existing high-energy Spectral.schema.json (which covers
PowerLaw / Band fits, fluence, flux density). SpectralLines captures the
optical-spectroscopy-specific rest/observed wavelengths and equivalent widths
of identified atomic transitions.

Future upstream PR: nasa-gcn/gcn-schema.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, RootModel


class SpectralLine(BaseModel):
    """One identified spectral line from an optical-spectroscopy observation."""

    line_id: str = Field(
        description=(
            "Identifier for the line, ex. 'Halpha', 'CaII H&K', 'OIII 5007', 'MgII 2796/2803'."
        ),
    )
    rest_wavelength: float | None = Field(
        default=None,
        description="Rest-frame wavelength of the transition [Angstrom].",
    )
    observed_wavelength: float | None = Field(
        default=None,
        description="Observed-frame wavelength as measured [Angstrom].",
    )
    equivalent_width: float | None = Field(
        default=None,
        description="Equivalent width [Angstrom]. Positive = emission, negative = absorption.",
    )


class SpectralLines(RootModel[list[SpectralLine]]):
    """A list of identified spectral lines from one spectrum."""
