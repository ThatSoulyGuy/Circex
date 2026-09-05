"""Tests for the taxonomy-aware classification matcher."""

from __future__ import annotations

from circex.extract.regex.classification import (
    parse_classification,
    parse_stellar_flare,
    parse_xrf_subtype,
)


def test_match_canonical_class() -> None:
    c = parse_classification("Spectroscopic typing confirms Ia.")
    assert c is not None and c.classification == "Ia"


def test_match_via_alias() -> None:
    # 'SNIa' is an alias for 'Ia' in supernovae.yaml.
    c = parse_classification("Classified as SNIa from absorption lines.")
    assert c is not None
    assert c.classification == "Ia"


def test_match_longer_alias_wins_at_position() -> None:
    # If both 'Ic' and 'Ic-BL' could match at the same position, the longer alias wins.
    c = parse_classification("This is an Ic-BL with broad lines.")
    assert c is not None
    assert c.classification == "Ic-BL"


def test_no_match_when_no_taxonomy_word() -> None:
    assert parse_classification("Just plain text with no class names.") is None


def test_match_tde_alias() -> None:
    c = parse_classification("Likely a TDE based on the X-ray follow-up.")
    assert c is not None
    # 'TDE' is the alias; canonical is 'Tidal Disruption Event'.
    assert c.classification == "Tidal Disruption Event"


# ---- short-alias false-positive guard (GRB 260604C flurry; docs/flurry_test_grb260604c.md) ----


def test_author_initial_is_not_a_classification() -> None:
    """1-char aliases are dropped: 'O.' (O. Spiridonova) must not become 'Overtone'."""
    assert parse_classification("A. Moskvitin, O. Spiridonova report observations.") is None


def test_substring_two_char_alias_without_context_rejected() -> None:
    """'in' (an Orion alias) in plain prose, no classification cue -> not Orion.

    (The sentence avoids other taxonomy words; we assert the specific
    false-positive the guard targets does not occur.)"""
    c = parse_classification("The optical counterpart brightened in our latest frames.")
    assert c is None or c.classification != "Orion"


def test_two_char_alias_initial_rejected() -> None:
    """'Fu' (FU Ori alias) as a name fragment, no cue -> no match."""
    assert parse_classification("Observations reported by Fu et al. last night.") is None


def test_two_char_alias_with_context_accepted() -> None:
    """A real 2-char class with a classification cue is still matched."""
    c = parse_classification("The spectrum is consistent with a Type Ia event.")
    assert c is not None and c.classification == "Ia"


def test_bare_two_char_alias_without_context_rejected() -> None:
    assert parse_classification("the transient is Ia") is None


# ---- hyphenated-proper-noun guard (the "Kilonova-Catcher" telescope name) ----


def test_kilonova_in_telescope_name_is_not_a_classification() -> None:
    """'Kilonova' inside the telescope name 'Kilonova-Catcher' must not classify."""
    c = parse_classification("Kilonova-Catcher reports an optical afterglow detection.")
    assert c is None or c.classification != "kilonova"


def test_kilonova_like_modifier_is_kept() -> None:
    """A real classification phrase 'kilonova-like' (lowercase suffix) is kept."""
    c = parse_classification("The spectrum is consistent with a kilonova-like transient.")
    assert c is not None and c.classification == "kilonova"


def test_single_letter_subtype_suffix_is_kept() -> None:
    """'Type II-P' keeps the base class (single-letter subtype, not a proper noun)."""
    c = parse_classification("Classified as a Type II-P supernova.")
    assert c is not None and c.classification == "Type II"


def test_a_stated_x_ray_flash_is_a_subtype():
    assert parse_xrf_subtype("Therefore this burst is an XRF.") == "XRF"
    assert (
        parse_xrf_subtype("It is not detected above 40 keV, which classifies it as an XRF.")
        == "XRF"
    )


def test_a_hedged_x_ray_flash_is_a_candidate():
    assert (
        parse_xrf_subtype("Therefore this burst could be classified as an X-Ray Flash (XRF).")
        == "XRF candidate"
    )
    assert (
        parse_xrf_subtype("we conclude the burst is either an X-Ray Flash or a hard burst.")
        == "XRF candidate"
    )


def test_a_named_x_ray_flash_is_not_a_classification():
    """A designation or a cited burst names an XRF without classifying this one."""
    assert parse_xrf_subtype("this is the optical counterpart of XRF 050406.") is None
    assert parse_xrf_subtype("similar to that seen in GRB/XRF 060218 (Campana et al.).") is None
    assert parse_xrf_subtype("to look for any coincident hard X-ray flash.") is None


def test_a_refusal_to_conclude_is_not_a_classification():
    assert (
        parse_xrf_subtype("it is not possible to conclude that this event is an X-ray flash.")
        is None
    )


def test_a_trigger_stated_to_be_a_flaring_star():
    assert parse_stellar_flare("BAT triggered on the flare star Algol.") == "UV Ceti"
    assert (
        parse_stellar_flare("Hence we confirm that this EP trigger is due to the flaring star.")
        == "UV Ceti"
    )


def test_a_hedged_flaring_star_is_a_candidate():
    assert (
        parse_stellar_flare(
            "The EP-WXT trigger is likely a stellar flare associated with LP 296-57."
        )
        == "UV Ceti candidate"
    )


def test_a_flare_star_that_is_not_the_classification():
    """A flare star can be a position reference, a comparison, or a rejected guess."""
    assert (
        parse_stellar_flare("This position is 2.9 arcsec from the known flare star DG CVn.") is None
    )
    assert parse_stellar_flare("Decline is similar to M-dwarf flare decline rate.") is None
    assert (
        parse_stellar_flare("there is a flare star system BD-21 1074 in the MAXI error box.")
        is None
    )
    assert (
        parse_stellar_flare("we see no signs of activity from the RS CVn flare star HR 5110.")
        is None
    )


def test_refusing_to_rule_a_flare_out_is_not_a_classification():
    assert (
        parse_stellar_flare(
            "Hence, the possibility that EP241107a is a stellar flare event cannot be ruled out."
        )
        is None
    )
