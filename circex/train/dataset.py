"""Build Mistral instruction-tuning datasets from labeled circulars.

Emits chat-format JSONL — one example per line, a user turn asking for structured
extraction of a circular and an assistant turn with the target JSON. Sources:

  - the Vidushi / Swift gold (event + redshift + telescope, 13.6k validated rows),
  - a directory of hand `.label.json` extractions plus their source bodies (the
    output of the `circex annotate` -> human-validation pipeline).

For a production fine-tune the user prompt should mirror the OllamaExtractor's
inference prompt so training and serving match — kept compact and aligned here;
that swap belongs in the training config, not the dataset.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

from circex.schema import CircularExtraction

INSTRUCTION = (
    "You are extracting structured data from a GCN optical astronomy circular. "
    "Return a compact JSON object with the transient's fields (event_name, "
    "localization, photometry, classification, redshift). Use null for anything "
    "the circular does not state. Do not invent values.\n\nCircular:\n"
)

# Schema keys that are bookkeeping, not extraction targets.
_DROP_KEYS = {"circular_id", "extraction_meta", "provenance"}


def _target_json(extraction: CircularExtraction) -> str:
    """The completion: the extraction's meaningful fields as compact JSON."""
    dump = extraction.model_dump(mode="json", by_alias=False, exclude_none=True)
    for key in _DROP_KEYS:
        dump.pop(key, None)
    return json.dumps(dump, ensure_ascii=False, separators=(",", ":"))


def to_example(text: str, extraction: CircularExtraction) -> dict[str, Any]:
    """One chat-format fine-tuning example (user = prompt+body, assistant = target)."""
    return {
        "messages": [
            {"role": "user", "content": INSTRUCTION + text},
            {"role": "assistant", "content": _target_json(extraction)},
        ]
    }


def _has_signal(extraction: CircularExtraction) -> bool:
    """True if the extraction carries at least one populated target field."""
    return any(
        (
            extraction.event is not None and extraction.event.event_name is not None,
            extraction.localization is not None,
            bool(extraction.photometry),
            extraction.classification is not None,
            extraction.redshift is not None,
        )
    )


def vidushi_examples(
    rows: Iterable[Any], *, require_signal: bool = True
) -> Iterator[dict[str, Any]]:
    """Fine-tuning examples from Vidushi/Swift gold rows (each has `.text` + gold)."""
    from circex.eval.vidushi_adapter import vidushi_gold_extraction

    for row in rows:
        text = getattr(row, "text", None)
        if not text or not text.strip():
            continue
        extraction = vidushi_gold_extraction(row)
        if require_signal and not _has_signal(extraction):
            continue
        yield to_example(text, extraction)


def label_dir_examples(
    label_dir: Path,
    body_lookup: Callable[[int], str | None],
    *,
    require_signal: bool = True,
) -> Iterator[dict[str, Any]]:
    """Fine-tuning examples from a dir of `.label.json` extractions + their bodies."""
    for path in sorted(label_dir.glob("*.label.json")):
        extraction = CircularExtraction.model_validate_json(path.read_text(encoding="utf-8"))
        if require_signal and not _has_signal(extraction):
            continue
        body = body_lookup(extraction.circular_id)
        if not body:
            continue
        yield to_example(body, extraction)


def write_jsonl(
    examples: Iterable[dict[str, Any]],
    out_dir: Path,
    *,
    val_every: int = 10,
) -> tuple[int, int]:
    """Write train/val JSONL under out_dir. Deterministic split: every Nth -> val.

    Returns (n_train, n_val). `val_every=10` holds out ~10%; the split is index
    based (no RNG) so a rebuild is reproducible.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    train_path = out_dir / "train.jsonl"
    val_path = out_dir / "val.jsonl"
    n_train = n_val = 0
    with (
        train_path.open("w", encoding="utf-8") as train_f,
        val_path.open("w", encoding="utf-8") as val_f,
    ):
        for i, example in enumerate(examples):
            line = json.dumps(example, ensure_ascii=False) + "\n"
            if val_every > 0 and i % val_every == 0:
                val_f.write(line)
                n_val += 1
            else:
                train_f.write(line)
                n_train += 1
    return n_train, n_val
