"""Pydantic v2 schema for CircularExtraction.

Mirrors the existing gcn-schema core schemas (Event, FollowUp, Localization, DateTime,
Redshift, Reporter), extends Photometry, and adds two new schemas (SpectralLines,
Classification). The dumped JSON Schemas are the artifacts of a future upstream PR
against nasa-gcn/gcn-schema.
"""

from circex.schema.circular_extraction import CircularExtraction
from circex.schema.classification import Classification
from circex.schema.datetime_ import DateTime
from circex.schema.event import Event
from circex.schema.extraction_meta import ExtractionMeta
from circex.schema.follow_up import FollowUp
from circex.schema.localization import Localization
from circex.schema.photometry import (
    CalibrationReference,
    FluxDensityUnit,
    MagSystem,
    PhotometryExt,
)
from circex.schema.redshift import Redshift, RedshiftMeasure, RedshiftType
from circex.schema.reporter import Messenger, Reporter, SpectralBandUnit
from circex.schema.span import Span
from circex.schema.spectral_lines import SpectralLine, SpectralLines
from circex.schema.time_offset import TimeOffset, TimeOffsetUnit

__all__ = [
    "CalibrationReference",
    "CircularExtraction",
    "Classification",
    "DateTime",
    "Event",
    "ExtractionMeta",
    "FollowUp",
    "Localization",
    "FluxDensityUnit",
    "MagSystem",
    "Messenger",
    "PhotometryExt",
    "Redshift",
    "RedshiftMeasure",
    "RedshiftType",
    "Reporter",
    "Span",
    "SpectralBandUnit",
    "SpectralLine",
    "SpectralLines",
    "TimeOffset",
    "TimeOffsetUnit",
]
