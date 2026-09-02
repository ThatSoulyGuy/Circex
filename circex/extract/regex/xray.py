"""X-ray and gamma-ray photometry: energy flux over a stated band.

High-energy circulars report a band-integrated energy flux ("The derived
0.5-10 keV upper limit is about 1.0e-13 erg cm^-2 s^-1"), so neither `filter`
nor `mag` applies and the band is identified by its energy range.

Two neighbouring quantities share the word "erg" and are not photometry: a
fluence carries no per-second term (erg cm^-2) and a luminosity no per-area term
(erg s^-1). Both are rejected by requiring cm^-2 and s^-1 in the unit.
"""

from __future__ import annotations

import re
from typing import Final

from circex.extract.regex.mag_table import _contaminant_ranges, _in_ranges
from circex.schema import PhotometryExt, Span

# Instrument mention -> bandpass. The instrument names the band far more
# reliably than the quoted energy range, which overlaps across missions:
# 0.5-10 keV fits EP-FXT, SVOM MXT and Swift XRT equally well.
_INSTRUMENT_BANDPASS: Final[tuple[tuple[str, str], ...]] = (
    (r"EP[-/\s]?WXT|\bWXT\b", "epwxt"),
    (r"EP[-/\s]?FXT|\bFXT\b", "epfxt"),
    (r"SVOM[-/\s]?MXT|\bMXT\b", "svommxt"),
    (r"ECLAIRs", "svomeclairs"),
    (r"SVOM[-/\s]?GRM|\bGRM\b", "svomgrm"),
    (r"Swift[-/\s]?XRT|\bXRT\b", "swiftxrt"),
    (r"NICER|\bXTI\b", "nicerxti"),
    # Hard X-ray and gamma-ray monitors.
    (r"Swift[-/\s]?BAT|\bBAT\b", "swiftbat"),
    (r"Fermi[-/\s]?GBM|\bGBM\b", "fermigbm"),
    (r"Fermi[-/\s]?LAT|\bLAT\b", "fermilat"),
    (r"Konus[-\s]?Wind|\bKonus\b", "konus"),
    (r"SPI[-/\s]?ACS", "integralacs"),
    (r"IBIS[/\s]?ISGRI|\bISGRI\b|\bIBIS\b", "integralibis"),
    (r"JEM[-\s]?X", "integraljemx"),
    (r"CGBM|\bCALET\b", "caletcgbm"),
    (r"NuSTAR", "nustar"),
    (r"MAXI[-/\s]?GSC|\bMAXI\b", "maxigsc"),
)
_INSTRUMENT_RE: Final[tuple[tuple[re.Pattern[str], str], ...]] = tuple(
    (re.compile(pattern, re.IGNORECASE), band) for pattern, band in _INSTRUMENT_BANDPASS
)

# The fallback used when no instrument is named. Soft X-ray instruments cover
# nearly the same range, so the quoted band separates them hardly at all and the
# fallback resolves to Swift XRT, which reports most of the soft X-ray fluxes in
# the archive. Every other instrument has to be named: a 0.3-10 keV range is no
# evidence that EP observed, least of all in a circular predating its launch.
_BANDPASS_ENERGY: Final[tuple[tuple[float, float, str], ...]] = ((0.2, 12.4, "swiftxrt"),)

# "1.0e-13", "4 x 10^-14", "5e-7", "2.3 x 10-12"
_NUM = r"\d+(?:\.\d+)?(?:\s*[eE]\s*[-+]?\d+|\s*[x×]\s*10\s*[\^]?\s*[-+]?\d+)?"

# The unit must carry both cm^-2 and s^-1: a fluence (erg cm^-2) and a
# luminosity (erg s^-1) are not photometry.
_UNIT_RE = re.compile(
    r"erg\s*(?:/|\s)?\s*cm\s*[\^]?\s*-?\s*2\s*(?:/|\s)?\s*s\s*[\^]?\s*-?\s*1?"
    r"|erg\s*/\s*cm\s*\^?\s*2\s*/\s*s",
    re.IGNORECASE,
)

_BAND_RE = re.compile(
    r"(?P<lo>\d+(?:\.\d+)?)\s*[-–]\s*(?P<hi>\d+(?:\.\d+)?)\s*(?P<unit>keV|MeV|GeV)",
    re.IGNORECASE,
)

_VALUE_RE = re.compile(rf"(?P<val>{_NUM})", re.IGNORECASE)
_LIMIT_RE = re.compile(
    r"upper[\s-]?limit|\blimits?\b|not\s+detected|did\s+not\s+detect"
    r"|no\s+significant|non[\s-]?detection|no\s+(?:new\s+)?(?:X-ray\s+)?source",
    re.IGNORECASE,
)
_SIGMA_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-\s]?sigma", re.IGNORECASE)
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")

_KEV: Final[dict[str, float]] = {"kev": 1.0, "mev": 1.0e3, "gev": 1.0e6}

# Parenthesised or +/- uncertainties sitting between the value and its unit.
_ERROR_GROUP_RE = re.compile(
    r"\(\s*[+\-±][^)]*\)|\(\s*\+/-[^)]*\)|\s*(?:\+/-|±)\s*" + _NUM,
    re.IGNORECASE,
)

# An energy flux outside this range is a parse failure, not a measurement.
_PLAUSIBLE_FLUX: Final[tuple[float, float]] = (1.0e-20, 1.0e-2)


def _to_float(token: str) -> float | None:
    """Parse '4 x 10^-14', '1.0e-13' or '2.3' into a float."""
    text = re.sub(r"\s+", "", token)
    text = re.sub(r"[x×]10\^?", "e", text, flags=re.IGNORECASE)
    try:
        return float(text)
    except ValueError:
        return None


def bandpass_for_instrument(text: str) -> str | None:
    """Bandpass of the first instrument named in `text`, by position.

    Position matters: a follow-up circular opens with the instrument that
    observed and mentions others later as context, so GCN 45497 reads "EP-FXT
    performed a follow-up observation ... within the 2.4 arcmin radius of the
    EP-WXT position", where the flux belongs to FXT and WXT only supplied the
    localization.
    """
    best: tuple[int, str] | None = None
    for pattern, band in _INSTRUMENT_RE:
        match = pattern.search(text)
        if match is not None and (best is None or match.start() < best[0]):
            best = (match.start(), band)
    return best[1] if best is not None else None


def bandpass_for_band(lo_kev: float, hi_kev: float) -> str | None:
    """Bandpass whose energy range best overlaps [lo, hi], or None."""
    best, best_overlap = None, 0.0
    for b_lo, b_hi, name in _BANDPASS_ENERGY:
        overlap = min(hi_kev, b_hi) - max(lo_kev, b_lo)
        if overlap <= 0:
            continue
        fraction = overlap / (max(hi_kev, b_hi) - min(lo_kev, b_lo))
        if fraction > best_overlap + 1e-9:
            best, best_overlap = name, fraction
    return best if best_overlap >= 0.5 else None


def parse_xray_with_spans(text: str) -> list[tuple[PhotometryExt, Span]]:
    """X-ray energy-flux rows with Spans into the source text.

    One row per clause that states a flux, its unit, and an energy band. A
    clause missing any of the three yields nothing.
    """
    excluded = _contaminant_ranges(text)
    out: list[tuple[PhotometryExt, Span]] = []
    offset = 0
    for clause in _CLAUSE_SPLIT_RE.split(text):
        start = text.index(clause, offset)
        offset = start + len(clause)
        if _in_ranges(start, excluded):
            continue
        row = _parse_clause(clause, text)
        if row is not None:
            out.append((row, Span(start=start, end=start + len(clause), snippet=clause)))
    return out


def _parse_clause(clause: str, whole: str) -> PhotometryExt | None:
    unit = _UNIT_RE.search(clause)
    if unit is None:
        return None
    band = _BAND_RE.search(clause)
    if band is None:
        return None
    scale = _KEV[band.group("unit").lower()]
    lo = float(band.group("lo")) * scale
    hi = float(band.group("hi")) * scale
    if lo >= hi:
        return None

    # The flux value is the last number before the unit, once the energy band and
    # any uncertainty have been removed: "3.5e-12 +/- 2.1e-12" must not yield the
    # error, and "2.6 (+1.1, -0.9) e-14" must rejoin its mantissa and exponent.
    head = clause[: unit.start()]
    if band.end() <= unit.start():
        head = head[: band.start()] + " " * (band.end() - band.start()) + head[band.end() :]
    head = _ERROR_GROUP_RE.sub(" ", head)
    values = [v for v in (_to_float(m.group("val")) for m in _VALUE_RE.finditer(head)) if v]
    if not values:
        return None
    value = values[-1]
    if not _PLAUSIBLE_FLUX[0] < abs(value) < _PLAUSIBLE_FLUX[1]:
        return None

    is_limit = _LIMIT_RE.search(clause) is not None
    sigma_match = _SIGMA_RE.search(clause)
    bandpass = bandpass_for_instrument(clause) or bandpass_for_instrument(whole)
    if bandpass is None:
        bandpass = bandpass_for_band(lo, hi)

    row = PhotometryExt(
        energy_band_kev=[lo, hi],
        bandpass=bandpass,
        mag_system="AB",
    )
    if is_limit:
        row.limiting_energy_flux = value
        row.limiting_mag_sigma = float(sigma_match.group(1)) if sigma_match else 3.0
    else:
        row.energy_flux = value
    row.is_detection = not is_limit
    return row
