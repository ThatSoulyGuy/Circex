"""Retraction detection from the subject line."""

from __future__ import annotations

import pytest

from circex.extract.regex.retraction import is_retraction


@pytest.mark.parametrize(
    "subject",
    [
        "BAT trigger 778435 is not a GRB.",
        "Swift Trigger 781740 is not a burst",
        "Swift trigger 779171 is probably a noise fluctuation",
        "Swift Trigger 1232755: likely consistent with noise and not astrophysical",
        "Swift Triggers 1192480, 1192481 and 1192482 are not astrophysical events",
        "Retraction of high energy neutrino candidate IceCube-171028A",
        "Fermi GBM trigger 743243582/240721356 (GRB 240721A) is not a GRB",
    ],
)
def test_retraction_subjects(subject: str) -> None:
    assert is_retraction(subject)


@pytest.mark.parametrize(
    "subject",
    [
        "GRB 240603B: Swift-XRT afterglow detection",
        # "false alarm rate" is standard alert boilerplate, not a withdrawal.
        "IceCube-220907A - IceCube observation of a high-energy neutrino candidate",
        "GRB 221009A: Fermi GBM detection of an extraordinarily bright burst",
        "EP260901a: Einstein Probe FXT follow-up",
        None,
        "",
    ],
)
def test_ordinary_subjects_are_not_retractions(subject: str | None) -> None:
    assert not is_retraction(subject)
