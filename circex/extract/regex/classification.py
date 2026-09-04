"""Taxonomy-aware classification matcher.

Walks circex.taxonomy.alias_to_canonical() and scans body text for whole-token
matches against the alias list (longest-alias-first to avoid partial-match
collisions like 'Ia' matching inside 'kilonova').

Short aliases are the dominant false-positive source: the taxonomy includes
single- and two-letter aliases (e.g. 'O' for Overtone, 'M' for Mira) that match
author initials and stray substrings. The GRB 260604C flurry test produced ~9
garbage classifications out of 12 this way (see docs/flurry_test_grb260604c.md).
We guard against it with two rules:

  - 1-character aliases are dropped entirely (they never carry classification
    signal in prose and reliably match author initials).
  - 2-character aliases (e.g. 'Ia', 'Ib', 'Ic', 'II') only match when a
    classification-context cue ('type', 'classified', 'spectrum', 'supernova',
    'consistent with', ...) appears within a small window — which preserves
    'Type Ia' while rejecting 'in' (Orion) and 'Fu' (FU Ori) in GRB prose.

Aliases of 3+ characters match directly, except that a match which is the head
of a hyphenated proper noun (a trailing "-Capitalizedword", e.g. "Kilonova"
inside the telescope name "Kilonova-Catcher") is skipped. Single-letter subtype
suffixes ("II-P"), all-caps suffixes ("Ia-CSM"), and lowercase modifiers
("kilonova-like", "Ia-pec") are kept; real hyphenated classes (Ic-BL, Type II)
are aliases and match in full regardless.
"""

from __future__ import annotations

import re

from circex.schema import Classification, Span
from circex.taxonomy import alias_to_canonical

# Aliases this short or shorter are ambiguous; see module docstring.
# Taxonomy "other names" that are English words, observing bands, or bare
# letters. Upstream lists them for good reason (RS CVn stars emit in radio and
# X-ray; the class is written "BY Dra"), but as free-text triggers they fire on
# ordinary prose: over a 3,594-Circular sample, "x-ray" and "radio" alone
# produced 283 spurious RS CVn classifications, "by" 99 BY Dra, and "in" 54
# Orion. A classification only comes from a token that names a class.
_NON_TRIGGER_ALIASES = frozenset(
    {
        "radio",
        "x-ray",
        "xray",
        "gamma-ray",
        "optical",
        "infrared",
        "uv",
        "by",
        "in",
        "it",
        "at",
        "as",
        "is",
        "ep",
        "id",
        "ie",
        "be",
        "f",
        "m",
        "o",
        "ca ii",
        # Software, institutions and funding bodies that share a class alias:
        # "using SNID we classify", "Tata Institute of Fundamental Research",
        # "funding from DST-SERB", "Siding Spring Observatory (SSO)", and
        # "a classical long GRB".
        "snid",
        "fundamental",
        "dst",
        "sso",
        "classical",
    }
)

# Trailing acknowledgements name institutions, funders and facilities, none of
# which classify the transient. Everything from the first such phrase is ignored.
_ACKNOWLEDGEMENT_RE = re.compile(
    r"\b(?:we\s+(?:thank|acknowledge|are\s+grateful)|this\s+(?:work|research|"
    r"publication)\s+(?:was|is|has\s+been)\s+(?:supported|funded|made)|"
    r"based\s+on\s+observations\s+(?:made|obtained)\s+(?:with|at)|"
    r"funding\s+from|is\s+(?:supported|funded)\s+by\s+the)",
    re.IGNORECASE,
)

# A class named as the target of a search is not the classification of this
# event: "to look for any coincident hard X-ray flash".
_SEARCH_CONTEXT_RE = re.compile(
    r"(?:look(?:ing|ed)?\s+for|search(?:ing|ed)?\s+for|in\s+search\s+of)"
    r"(?:\s+\S+){0,6}\s*$",
    re.IGNORECASE,
)

_SHORT_ALIAS_MAX = 2
# Window (chars on each side) to look for a classification cue near a 2-char alias.
_CONTEXT_WINDOW = 60

# Classification-action cues. Deliberately excludes bare "SN" (appears in every
# SN designation) to avoid re-admitting the false positives this guard removes.
_CLASS_CONTEXT = re.compile(
    r"\b(?:typ(?:e|ed|ing)|classif\w*|spectrum|spectra|spectroscop\w*|"
    r"supernova|consistent\s+with|identif\w*|resembl\w*|template|best[-\s]?fit)\b",
    re.IGNORECASE,
)


def _build_alias_pattern() -> re.Pattern[str]:
    """Build one big alternation regex of all aliases >1 char, longest-first."""
    aliases = sorted((a for a in alias_to_canonical() if len(a) > 1), key=len, reverse=True)
    # Escape and anchor to word boundaries. Use case-insensitive matching.
    parts = [re.escape(alias) for alias in aliases]
    pattern = r"\b(?:" + "|".join(parts) + r")\b"
    return re.compile(pattern, re.IGNORECASE)


_ALIAS_PATTERN: re.Pattern[str] | None = None


def _alias_pattern() -> re.Pattern[str]:
    global _ALIAS_PATTERN  # noqa: PLW0603
    if _ALIAS_PATTERN is None:
        _ALIAS_PATTERN = _build_alias_pattern()
    return _ALIAS_PATTERN


def parse_classification(text: str) -> Classification | None:
    """Return the first canonical taxonomy class matched in the text, or None.

    Longest-alias-first ordering means 'Ic-BL' wins over 'Ic' when both could match.
    """
    result = parse_classification_with_span(text)
    return result[0] if result is not None else None


def parse_classification_with_span(
    text: str,
) -> tuple[Classification, Span] | None:
    """Same as parse_classification, plus a Span pointing at the alias match.

    Returns the first *accepted* match: short (<=2 char) aliases are only
    accepted with a nearby classification cue, so a stray author initial or
    substring is skipped rather than misclassifying the circular.
    """
    ack = _ACKNOWLEDGEMENT_RE.search(text)
    body_end = ack.start() if ack else len(text)
    for match in _alias_pattern().finditer(text):
        if match.start() >= body_end:
            break
        token = match.group(0)
        if token.lower() in _NON_TRIGGER_ALIASES:
            continue
        if _SEARCH_CONTEXT_RE.search(text[max(0, match.start() - 80) : match.start()]):
            continue
        canonical = alias_to_canonical().get(token.lower())
        if canonical is None:
            continue
        # Reject an alias that is the head of a hyphenated proper noun, e.g.
        # "Kilonova" inside the telescope name "Kilonova-Catcher". The tell is a
        # trailing "-" + a Capitalized word (uppercase then lowercase). Single-
        # letter subtype suffixes ("II-P", "II-L"), all-caps suffixes ("Ia-CSM"),
        # and lowercase modifiers ("kilonova-like", "Ia-pec") are kept. Real
        # hyphenated classes (Ic-BL, II-P, Type II) are aliases and match in full
        # above, so this only fires on partial matches of non-alias compounds.
        tail = text[match.end() : match.end() + 3]
        if len(tail) == 3 and tail[0] == "-" and tail[1].isupper() and tail[2].islower():
            continue
        if len(token) <= _SHORT_ALIAS_MAX:
            window = text[max(0, match.start() - _CONTEXT_WINDOW) : match.end() + _CONTEXT_WINDOW]
            if not _CLASS_CONTEXT.search(window):
                continue
        try:
            cls = Classification(classification=canonical)
        except ValueError:
            continue
        span = Span(start=match.start(), end=match.end(), snippet=token)
        return cls, span
    return None


# ---- X-ray flash ----
#
# XRF is not a taxonomy class, so it rides on `subtype` while `classification`
# stays GRB. Circulars name it three ways, and only one is a classification:
#   "Therefore this burst is an XRF."            <- classifies this burst
#   "the optical counterpart of XRF 050406"      <- a designation
#   "similar to that seen in GRB/XRF 060218"     <- a different burst, cited
_XRF = r"(?:X[-\s]?ray\s+flash(?:es)?|XRF)"

# "XRF 030723", "XRF/GRB 011030", "XRF 100316D" — a name, not a class.
_XRF_DESIGNATION_RE = re.compile(rf"{_XRF}\s*/?\s*(?:GRB\s*)?\d{{6}}", re.I)

# The burst is being classified, rather than merely mentioned.
_XRF_CLASSIFIES_RE = re.compile(
    rf"(?:\b(?:is|are|was|were)\s+(?:an?\s+)?(?:[\w-]+\s+){{0,3}}?{_XRF}\b"
    rf"|classif\w*\s+(?:it\s+)?(?:as\s+)?(?:an?\s+)?{_XRF}\b"
    rf"|{_XRF}\s+classification"
    rf"|consistent\s+with\s+(?:an?\s+){_XRF}\b)",
    re.I,
)

# Hedges that make it a candidate rather than a claim, read within the sentence
# that classifies: an adjacent sentence hedging something else does not count.
_XRF_HEDGE_RE = re.compile(
    r"\b(?:could|may|might|would|possibl[ey]|potential(?:ly)?|probable|probably"
    r"|either"
    r"|likely|suspect\w*|suggest\w*|appears?|seems?|candidate|if\b|had\s+it"
    r"|consistent\s+with|cannot\s+be\s+excluded)\b",
    re.I,
)

# An explicit refusal to classify is not a classification: "it is not possible
# to conclude that this event is an X-ray flash".
_XRF_NEGATED_RE = re.compile(
    r"\b(?:not\s+possible\s+to\s+conclude|cannot\s+(?:be\s+)?conclude\w*"
    r"|do(?:es)?\s+not\s+(?:appear|seem)|is\s+not\s+an?|no\s+evidence)\b",
    re.I,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def parse_xrf_subtype(text: str) -> str | None:
    """ "XRF", "XRF candidate", or None if the text classifies no X-ray flash."""
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        stripped = _XRF_DESIGNATION_RE.sub(" ", sentence)
        if not _XRF_CLASSIFIES_RE.search(stripped):
            continue
        if _SEARCH_CONTEXT_RE.search(stripped[: stripped.lower().find("x")]):
            continue
        if _XRF_NEGATED_RE.search(stripped):
            continue
        return "XRF candidate" if _XRF_HEDGE_RE.search(stripped) else "XRF"
    return None
