"""Map a CircularExtraction to SkyPortal API writes.

Pure functions, no network. `to_actions()` returns a SkyPortalActions bundle —
a source upsert, photometry points, an optional redshift patch, and comments —
shaped as the dicts SkyPortal's REST API expects. The poster turns these into
HTTP calls (or prints them in dry-run). See docs/design_skyportal_bot.md.

Everything the ICARE work added feeds in here: obs_mjd -> mjd, bandpass ->
filter, telescope_canonical -> instrument_id, is_detection, redshift bounds ->
comment, provenance -> altdata.note.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from circex.extract.regex.mag_table import (
    infer_bandpass,
    infer_mag_system,
    normalize_filter,
)
from circex.schema import CircularExtraction, PhotometryExt

# mag_system (our enum) -> SkyPortal magsys (lowercase). STMag has no direct
# SkyPortal equivalent; map to the closest and flag it in a comment upstream.
log = structlog.get_logger(__name__)

_MAGSYS = {"AB": "ab", "Vega": "vega", "STMag": "ab"}


def _obj_id(extraction: CircularExtraction) -> str | None:
    """SkyPortal source id from the event name (spaces removed). None if unnamed.

    Prefers an AT/optical designation over a bare GRB/GW trigger when the
    extraction carries a list (the optical name is what SkyPortal keys on).
    """
    if extraction.event is None or extraction.event.event_name is None:
        return None
    name = extraction.event.event_name
    names = name if isinstance(name, list) else [name]
    optical = [n for n in names if re.match(r"(?i)^(AT|SN)\s?\d", n)]
    chosen = optical[0] if optical else (names[0] if names else None)
    return re.sub(r"\s+", "", chosen) if chosen else None


@dataclass(frozen=True)
class SourceUpsert:
    """`POST /api/sources` payload."""

    id: str
    ra: float | None
    dec: float | None
    group_ids: list[int] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id}
        if self.ra is not None:
            out["ra"] = self.ra
        if self.dec is not None:
            out["dec"] = self.dec
        if self.group_ids:
            out["group_ids"] = self.group_ids
        return out


@dataclass(frozen=True)
class PhotometryPoint:
    """`POST /api/photometry` payload for one row."""

    obj_id: str
    mjd: float
    filter: str
    magsys: str
    instrument_id: int | None
    mag: float | None
    magerr: float | None
    limiting_mag: float | None
    altdata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "obj_id": self.obj_id,
            "mjd": self.mjd,
            "filter": self.filter,
            "magsys": self.magsys,
            "mag": self.mag,
            "magerr": self.magerr,
            "limiting_mag": self.limiting_mag,
        }
        if self.instrument_id is not None:
            out["instrument_id"] = self.instrument_id
        if self.altdata:
            out["altdata"] = self.altdata
        return out


@dataclass(frozen=True)
class SkyPortalActions:
    """Everything to post for one circular."""

    source: SourceUpsert | None
    photometry: list[PhotometryPoint]
    redshift: tuple[float, float | None] | None  # (z, z_err)
    comments: list[str]
    skipped_rows: int  # photometry rows we could not post (no mjd/filter)
    # The extractions these actions were built from. Callers that need fields with
    # no place in the SkyPortal write bundle (event designations, classification)
    # would otherwise have to run the extractor a second time.
    extractions: tuple[CircularExtraction, ...] = ()


def _provenance_note(extraction: CircularExtraction, path: str) -> str | None:
    span = extraction.provenance.get(path)
    return f'{path}: "{span.snippet}"' if span is not None else None


def to_actions(
    extraction: CircularExtraction,
    *,
    instrument_map: dict[str, int] | None = None,
    default_instrument_id: int | None = None,
    group_ids: list[int] | None = None,
) -> SkyPortalActions:
    """Build the SkyPortal write bundle for one extraction.

    `instrument_map` maps `telescope_canonical` -> SkyPortal instrument_id
    (ICARE's table). `default_instrument_id` is the generic GCN instrument used
    when a telescope isn't in the map (matching ICARE's fall-back). SkyPortal's
    photometry endpoint REQUIRES an instrument_id, so a row that resolves to
    neither a mapped nor a default id cannot be posted — it becomes a comment.
    """
    instrument_map = instrument_map or {}
    group_ids = group_ids or []

    obj_id = _obj_id(extraction)
    loc = extraction.localization
    ra = loc.ra if loc is not None else None
    dec = loc.dec if loc is not None else None

    photometry: list[PhotometryPoint] = []
    comments: list[str] = []
    skipped = 0

    # A NEW SkyPortal source requires ra/dec. A follow-up circular usually has no
    # position (it lives in the discovery circular), so guard against emitting a
    # positionless source-create that SkyPortal would reject with a 400.
    source: SourceUpsert | None = None
    if obj_id is not None and ra is not None and dec is not None:
        source = SourceUpsert(id=obj_id, ra=ra, dec=dec, group_ids=group_ids)
    elif obj_id is not None:
        comments.append(
            f"Source {obj_id} not created: no RA/Dec in this circular "
            f"(position comes from the discovery circular)."
        )

    for idx, row in enumerate(extraction.photometry):
        point = _row_to_point(extraction, obj_id, idx, row, instrument_map, default_instrument_id)
        if point is None:
            skipped += 1
        else:
            photometry.append(point)

    # Redshift: scalar only. Bounds (in notes) become a comment, not a value.
    redshift: tuple[float, float | None] | None = None
    if extraction.redshift is not None and extraction.redshift.redshift is not None:
        err = extraction.redshift.redshift_error
        z_err = err if isinstance(err, float) else None
        redshift = (extraction.redshift.redshift, z_err)
        if (note := _provenance_note(extraction, "redshift")) is not None:
            comments.append(f"Redshift z={extraction.redshift.redshift} from {note}")

    # Bound redshifts and other extractor notes -> comment.
    for note in extraction.extraction_meta.notes:
        comments.append(f"Note (not posted as a value): {note}")

    if skipped:
        comments.append(
            f"{skipped} photometry row(s) could not be posted "
            f"(missing observation time, filter, or instrument_id); "
            f"kept in the extraction only."
        )

    return SkyPortalActions(
        source=source,
        photometry=photometry,
        redshift=redshift,
        comments=comments,
        skipped_rows=skipped,
        extractions=(extraction,),
    )


def _effective_band(row: PhotometryExt) -> tuple[str | None, str]:
    """Canonical (bandpass, magsys) for a row.

    The deterministic filter crosswalk is authoritative for recognized filters
    and OVERRIDES the extractor's values — an LLM may mislabel a band (e.g.
    Mistral tagging Cousins "Rc" as sdssr/ab when it is bessellr/vega). Falls
    back to the row's own bandpass/mag_system when the filter isn't recognized.
    """
    base = normalize_filter(row.filter) if row.filter else None
    band = infer_bandpass(base) if base else None
    if band is not None:
        system = infer_mag_system(base) if base else None
        return band, _MAGSYS.get(system or "", "ab")
    return row.bandpass, _MAGSYS.get(row.mag_system or "", "ab")


def _row_to_point(
    extraction: CircularExtraction,
    obj_id: str | None,
    idx: int,
    row: PhotometryExt,
    instrument_map: dict[str, int],
    default_instrument_id: int | None,
) -> PhotometryPoint | None:
    """One photometry row -> a SkyPortal point, or None if unpostable.

    A row needs an obj_id, an obs_mjd, a resolvable bandpass, AND an
    instrument_id (mapped, or the generic default) — SkyPortal requires all of
    these. Otherwise it cannot be posted.
    """
    band, magsys = _effective_band(row)
    mapped = instrument_map.get(row.telescope_canonical) if row.telescope_canonical else None
    instrument_id = mapped if mapped is not None else default_instrument_id
    if obj_id is None or row.obs_mjd is None or band is None or instrument_id is None:
        # Name the reason: a filter with no bandpass is a crosswalk gap and the
        # row is lost silently otherwise, which reads as a thin light curve
        # rather than as missing data.
        log.info(
            "photometry_row_dropped",
            circular_id=extraction.circular_id,
            reason=(
                "no bandpass"
                if band is None
                else "no obs_mjd"
                if row.obs_mjd is None
                else "no obj_id"
                if obj_id is None
                else "no instrument_id"
            ),
            filter=row.filter,
            telescope=row.telescope,
        )
        return None

    # SkyPortal's photometry endpoint REQUIRES a non-null limiting_mag for
    # mag-space points. Circulars often report a detection with no explicit
    # per-point limit, so fall back to the detection mag itself — a conservative,
    # truthful depth floor (the field was seen at least this faint) — and flag it.
    limiting_mag = row.limiting_mag
    limit_assumed = False
    if limiting_mag is None:
        if row.mag is None:
            return None  # neither a detection nor a stated limit — nothing to post
        limiting_mag = row.mag
        limit_assumed = True

    altdata: dict[str, Any] = {}
    if (note := _provenance_note(extraction, f"photometry[{idx}]")) is not None:
        altdata["note"] = note
    altdata["circex_circular_id"] = extraction.circular_id
    if mapped is None:
        # Fell back to the generic instrument; record what we actually saw.
        altdata["instrument_fallback"] = True
        if row.telescope:
            altdata["telescope_as_written"] = row.telescope
    if limit_assumed:
        altdata["limiting_mag_assumed"] = True
    return PhotometryPoint(
        obj_id=obj_id,
        mjd=row.obs_mjd,
        filter=band,
        magsys=magsys,
        instrument_id=instrument_id,
        mag=row.mag,
        magerr=row.mag_error,
        limiting_mag=limiting_mag,
        altdata=altdata,
    )
