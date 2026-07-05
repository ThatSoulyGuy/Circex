"""Tests for the SN-type Naive Bayes classifier + harvester."""

from __future__ import annotations

from circex.classify import NONE_LABEL, SNTypeClassifier, label_of


def _train() -> SNTypeClassifier:
    texts = [
        "SN 2020aaa spectrum matches a type Ia supernova classified by SNID at z=0.05",
        "spectroscopy shows a type Ia supernova near maximum light",
        "the transient is a type II supernova with broad hydrogen H-alpha",
        "type II supernova, strong Balmer emission",
        "GRB 200101A optical afterglow detection r = 19.2, no classification",
        "GRB 200102A X-ray afterglow localization by Swift-XRT",
    ]
    labels = ["Ia", "Ia", "II", "II", NONE_LABEL, NONE_LABEL]
    return SNTypeClassifier.fit(texts, labels, min_count=1)


def test_classifier_predicts_types() -> None:
    clf = _train()
    assert clf.predict_type("a clear type Ia supernova match from SNID") == "Ia"
    assert clf.predict_type("type II supernova with strong hydrogen lines") == "II"


def test_classifier_abstains_on_non_classification() -> None:
    clf = _train()
    assert clf.predict("GRB 200103A optical afterglow detection r = 20") == NONE_LABEL
    assert clf.predict_type("GRB 200103A optical afterglow detection r = 20") is None


def test_save_load_roundtrip(tmp_path) -> None:
    clf = _train()
    path = tmp_path / "m.json"
    clf.save(path)
    loaded = SNTypeClassifier.load(path)
    text = "a clear type Ia supernova match from SNID"
    assert loaded.predict(text) == clf.predict(text)


def test_label_of_extracts_sn_types() -> None:
    assert label_of("The spectrum matches a type Ia supernova.") == {"Ia"}
    assert label_of("SNID gives a good match with a type Ic supernova") == {"Ic"}
    assert label_of("we report a tidal disruption event (TDE)") == {"Tidal Disruption Event"}


def test_label_of_excludes_grb_duration_type() -> None:
    """GRB 'type I/II' is short/long population, NOT an SN classification."""
    assert label_of("we classify the burst as type II (long) population") == set()
    assert label_of("the burst belongs to the type I (short) population") == set()
