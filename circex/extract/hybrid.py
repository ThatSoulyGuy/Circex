"""HybridExtractor — per-field routing between regex and a grammar-constrained LLM.

Each field is served by whichever extractor's *failure mode that field can
tolerate*. This is the production system the four-way eval points to: a regular
expression is precise on lexically regular / structured fields and silent on
semantically mediated ones, while a constrained language model is the reverse.
Routing each field to its stronger extractor dominates either one alone.

The routing table below is grounded in a measured bake-off on 805 optical
circulars:

  - event names       -> regex   (regex emits fewer false-positive designations)
  - coordinates       -> regex   (the LLM emits 0% localizations as prompted;
                                   regex converts sexagesimal -> degrees)
  - photometry        -> LLM     (2,648 rows vs 964 — reads prose + odd tables)
  - classification    -> LLM     (regex classification is event-type defaults
                                   plus star-name contaminants — precision-poor)
  - redshift          -> LLM     (constrained F1 0.935 > regex 0.862)

For fields where both can contribute, the routing is primary -> secondary: the
secondary fills in only when the primary produced nothing. Provenance spans are
carried over from whichever extractor supplied each field, so the merged result
round-trips through ``to_label_fields`` for snippet-level human validation.
"""

from __future__ import annotations

from circex.extract.protocol import Circular, Extractor
from circex.schema import CircularExtraction, ExtractionMeta
from circex.schema.span import Span

# field name -> (primary source, secondary source | None). Source is "regex" | "llm".
# A field taken from a source also inherits that source's provenance spans.
_ROUTING: dict[str, tuple[str, str | None]] = {
    "event": ("regex", "llm"),  # fewer false-positive designations
    "localization": ("regex", None),  # LLM emits no coordinates as prompted
    "follow_up": ("llm", "regex"),
    "datetime_": ("llm", "regex"),
    "time_offsets": ("llm", None),  # only the LLM produces these
    "photometry": ("llm", "regex"),  # 2,648 vs 964 rows
    "spectroscopy": ("llm", "regex"),
    "classification": ("llm", None),  # regex classification is defaults + contaminants
    "redshift": ("llm", "regex"),  # constrained F1 0.935 > regex 0.862
    "reporter": ("llm", "regex"),
}


def _present(value: object) -> bool:
    """A field counts as populated when it is neither None nor an empty list."""
    return value is not None and value != []


def _provenance_for(source: CircularExtraction, field: str) -> dict[str, Span]:
    """Provenance entries from ``source`` that belong to ``field``.

    Keys are dotted/indexed paths (``localization.ra``, ``photometry[0]``); the
    base segment before the first ``.`` or ``[`` names the top-level field. The
    ``datetime_`` field is stored under the ``datetime`` provenance base.
    """
    accepted = {field, field.rstrip("_")}
    out: dict[str, Span] = {}
    for key, span in source.provenance.items():
        base = key.split(".", 1)[0].split("[", 1)[0]
        if base in accepted:
            out[key] = span
    return out


class HybridExtractor(Extractor):
    """Merge a regex extractor and an LLM extractor by the per-field routing table."""

    def __init__(self, regex: Extractor, llm: Extractor) -> None:
        self._regex = regex
        self._llm = llm

    @property
    def extractor_id(self) -> str:
        return f"hybrid:{self._regex.extractor_id}+{self._llm.extractor_id}"

    def extract(self, circular: Circular) -> CircularExtraction:
        sources = {"regex": self._regex.extract(circular), "llm": self._llm.extract(circular)}
        fields: dict[str, object] = {"circular_id": circular.circular_id}
        provenance: dict[str, Span] = {}

        for field, (primary, secondary) in _ROUTING.items():
            value = getattr(sources[primary], field)
            chosen = primary if _present(value) else None
            if chosen is None and secondary is not None:
                alt = getattr(sources[secondary], field)
                if _present(alt):
                    value, chosen = alt, secondary
            fields[field] = value
            if chosen is not None:
                provenance.update(_provenance_for(sources[chosen], field))

        fields["provenance"] = provenance
        fields["extraction_meta"] = ExtractionMeta(
            extractor=self.extractor_id,
            model_id=getattr(self._llm, "model_id", None),
            prompt_version=getattr(self._llm, "prompt_version", None),
        )
        return CircularExtraction(**fields)  # type: ignore[arg-type]
