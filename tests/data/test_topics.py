"""Tests for circex.data.topics."""

from __future__ import annotations

from pathlib import Path

from circex.data.topics import OPTICAL_LABEL, load_optical_ids, load_topic_labels


def _write_topics_csv(path: Path) -> None:
    path.write_text(
        "Circular ID,Subject,Date,Label\n"
        "-4.0,bad row,1997-08-14 00:00:00,Optical Observations\n"  # negative ID — skipped
        "0,zero ID,1997-08-15 00:00:00,Optical Observations\n"  # zero ID — skipped
        "5,real optical,2020-01-01 00:00:00,Optical Observations\n"
        "6,non-integer,2020-01-02 00:00:00,Optical Observations\n"
        "7,radio,2020-01-03 00:00:00,Radio Observations\n"
        "8,high energy,2020-01-04 00:00:00,High Energy Observations\n"
        "9,optical 2,2020-01-05 00:00:00,Optical Observations\n",
        encoding="utf-8",
    )


def test_load_topic_labels_skips_malformed(tmp_path: Path) -> None:
    path = tmp_path / "topics.csv"
    _write_topics_csv(path)
    records = list(load_topic_labels(path))
    cids = [r.circular_id for r in records]
    # -4.0 and 0 skipped; 5, 6, 7, 8, 9 kept.
    assert cids == [5, 6, 7, 8, 9]


def test_load_optical_ids_filters_correctly(tmp_path: Path) -> None:
    path = tmp_path / "topics.csv"
    _write_topics_csv(path)
    ids = load_optical_ids(path)
    assert ids == [5, 6, 9]


def test_optical_label_constant() -> None:
    assert OPTICAL_LABEL == "Optical Observations"
