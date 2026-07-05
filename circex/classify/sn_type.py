"""Multinomial Naive Bayes SN-type classifier — dependency-free and deterministic.

Text in, one of {NONE, Ia, Ib, Ic, II, IIn, SLSN, TDE, …} out. Chosen over a
transformer deliberately: the signal is lexical ("type Ia", "broad-lined Ic",
"tidal disruption"), the data is small, and this trains in milliseconds on CPU
with a closed-form (RNG-free) fit — so it runs in CI and on the Mac, and the
Classification schema/interface make a transformer a later drop-in.

The decisive feature over the regex baseline is the **NONE** class: the regex
classifier fires on nearly every circular (precision ~0.10); trained on real
negatives (GRB / afterglow / detection circulars that carry no SN type), NB
learns to abstain.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

NONE_LABEL = "NONE"

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9-]+")


def _tokens(text: str) -> list[str]:
    """Lowercase word unigrams + adjacent bigrams (captures 'type ia', 'broad-lined')."""
    words = _TOKEN_RE.findall(text.lower())
    bigrams = [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]
    return words + bigrams


class SNTypeClassifier:
    """Multinomial Naive Bayes over token counts, with Laplace smoothing."""

    def __init__(
        self,
        classes: list[str],
        class_log_prior: dict[str, float],
        feature_log_prob: dict[str, dict[str, float]],
        default_log_prob: dict[str, float],
    ) -> None:
        self.classes = classes
        self.class_log_prior = class_log_prior
        self.feature_log_prob = feature_log_prob
        self.default_log_prob = default_log_prob

    @classmethod
    def fit(
        cls,
        texts: list[str],
        labels: list[str],
        *,
        alpha: float = 1.0,
        min_count: int = 2,
    ) -> SNTypeClassifier:
        """Train from (text, label) pairs. Deterministic — pure counting."""
        classes = sorted(set(labels))
        n_docs = Counter(labels)
        token_counts: dict[str, Counter[str]] = {c: Counter() for c in classes}
        total_tokens: dict[str, int] = dict.fromkeys(classes, 0)
        global_count: Counter[str] = Counter()
        per_doc_tokens = [(_tokens(t), lab) for t, lab in zip(texts, labels, strict=True)]
        for toks, _lab in per_doc_tokens:
            global_count.update(toks)
        vocab = {tok for tok, c in global_count.items() if c >= min_count}
        for toks, lab in per_doc_tokens:
            kept = [t for t in toks if t in vocab]
            token_counts[lab].update(kept)
            total_tokens[lab] += len(kept)

        n = len(texts)
        v = len(vocab)
        class_log_prior = {c: math.log(n_docs[c] / n) for c in classes}
        feature_log_prob: dict[str, dict[str, float]] = {}
        default_log_prob: dict[str, float] = {}
        for c in classes:
            denom = total_tokens[c] + alpha * v
            default_log_prob[c] = math.log(alpha / denom)
            feature_log_prob[c] = {
                tok: math.log((count + alpha) / denom)
                for tok, count in token_counts[c].items()
            }
        return cls(classes, class_log_prior, feature_log_prob, default_log_prob)

    def scores(self, text: str) -> dict[str, float]:
        toks = _tokens(text)
        out: dict[str, float] = {}
        for c in self.classes:
            flp = self.feature_log_prob[c]
            default = self.default_log_prob[c]
            score = self.class_log_prior[c]
            for tok in toks:
                score += flp.get(tok, default)
            out[c] = score
        return out

    def predict(self, text: str) -> str:
        """Most likely label (may be NONE)."""
        scores = self.scores(text)
        return max(scores, key=lambda c: scores[c])

    def predict_type(self, text: str) -> str | None:
        """The SN type, or None when the classifier abstains (predicts NONE)."""
        label = self.predict(text)
        return None if label == NONE_LABEL else label

    def to_dict(self, *, ndigits: int = 4) -> dict[str, Any]:
        """Serializable form; log-probs rounded to keep the model file compact."""
        return {
            "classes": self.classes,
            "class_log_prior": {c: round(v, ndigits) for c, v in self.class_log_prior.items()},
            "feature_log_prob": {
                c: {t: round(v, ndigits) for t, v in flp.items()}
                for c, flp in self.feature_log_prob.items()
            },
            "default_log_prob": {c: round(v, ndigits) for c, v in self.default_log_prob.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SNTypeClassifier:
        return cls(
            data["classes"],
            data["class_log_prior"],
            data["feature_log_prob"],
            data["default_log_prob"],
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict()), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> SNTypeClassifier:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
