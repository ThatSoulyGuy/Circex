"""Corpus + ground-truth loaders. All inputs come from references/circulars-nlp-paper/."""

from circex.data.archive import iter_circulars, untar_archive
from circex.data.subset import build_stratified_subset, load_subset
from circex.data.swift_gold import load_swift_evaluation
from circex.data.topics import load_optical_ids, load_topic_labels

__all__ = [
    "build_stratified_subset",
    "iter_circulars",
    "load_optical_ids",
    "load_subset",
    "load_swift_evaluation",
    "load_topic_labels",
    "untar_archive",
]
