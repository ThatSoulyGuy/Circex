"""ClaudeExtractor — tool-use forced structured output via the Anthropic SDK.

The `submit_extraction` tool's input_schema IS the JSON Schema of
CircularExtraction (minus circular_id + extraction_meta — those are runner-
filled). Forcing tool_use eliminates the "model emits prose around JSON"
failure mode.

System text + tool definition + few-shots are marked cache_control: ephemeral
so Anthropic prompt caching saves cost on repeated calls (5-minute TTL).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Final

import anthropic
import structlog

from circex.cache.llm import LLMCache, cache_key
from circex.extract.llm.chunker import chunk_body, merge_extractions
from circex.extract.llm.prompt import (
    PROMPT_V1,
    build_messages,
    build_system_text,
    llm_input_schema,
)
from circex.extract.protocol import Circular, Extractor
from circex.extract.timing import resolve_relative_epochs
from circex.schema import CircularExtraction, ExtractionMeta

if TYPE_CHECKING:
    from collections.abc import Iterable

log = structlog.get_logger(__name__)

# Approximate per-million-token pricing (USD). Sourced manually 2026-05; verify
# at Sprint 4 close before the cost-projection deliverable.
# See docs/known_issues.md "Claude pricing constants may be stale".
_PRICING: Final[dict[str, dict[str, float]]] = {
    "claude-haiku-4-5-20251001": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10,
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
}

_DEFAULT_MAX_TOKENS = 4096


def _compute_cost(model_id: str, usage: Any) -> float | None:
    """Compute USD cost from a response.usage object. None if model is unpriced."""
    prices = _PRICING.get(model_id)
    if prices is None:
        return None
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cost = (
        input_tokens * prices["input"]
        + output_tokens * prices["output"]
        + cache_write * prices["cache_write"]
        + cache_read * prices["cache_read"]
    ) / 1_000_000.0
    return cost


class ClaudeExtractor(Extractor):
    """LLM extractor backed by Anthropic Claude."""

    def __init__(
        self,
        model_id: str,
        cache: LLMCache | None = None,
        client: anthropic.Anthropic | None = None,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self._model_id = model_id
        self._cache = cache
        self._client = client or anthropic.Anthropic()
        self._max_tokens = max_tokens

    @property
    def extractor_id(self) -> str:
        return f"claude:{self._model_id}"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def prompt_version(self) -> str:
        return PROMPT_V1

    def extract(self, circular: Circular) -> CircularExtraction:
        body_hash = cache_key(circular.body)

        if self._cache is not None:
            cached = self._cache.get(
                self.extractor_id, self._model_id, PROMPT_V1, circular.circular_id, body_hash
            )
            if cached is not None:
                meta = cached.extraction.extraction_meta.model_copy(update={"cache_hit": True})
                result = cached.extraction.model_copy(update={"extraction_meta": meta})
                # Relative epochs are resolved per-call (T0-dependent), not cached.
                resolve_relative_epochs(result, circular.trigger_time)
                return result

        chunks = chunk_body(circular.body)

        started = time.perf_counter()
        chunk_results: list[CircularExtraction] = []
        total_tokens_in = 0
        total_tokens_out = 0
        total_cost = 0.0

        for chunk in chunks:
            payload, usage = self._call_api(
                Circular(
                    circular_id=circular.circular_id,
                    subject=circular.subject,
                    body=chunk,
                    event_id=circular.event_id,
                )
            )
            payload["circular_id"] = circular.circular_id
            # Preserve any `notes` Claude emitted (e.g. redshift_bound phrases)
            # while overwriting the run-level fields. Notes flow through the
            # chunker merge step back into the final extraction_meta.
            llm_meta = payload.get("extraction_meta") or {}
            llm_notes = llm_meta.get("notes", []) if isinstance(llm_meta, dict) else []
            if not isinstance(llm_notes, list):
                llm_notes = []
            payload["extraction_meta"] = {
                "extractor": self.extractor_id,
                "model_id": self._model_id,
                "notes": llm_notes,
            }
            chunk_results.append(CircularExtraction.model_validate(payload))

            total_tokens_in += getattr(usage, "input_tokens", 0) or 0
            total_tokens_out += getattr(usage, "output_tokens", 0) or 0
            cost = _compute_cost(self._model_id, usage)
            if cost is not None:
                total_cost += cost

        latency_ms = (time.perf_counter() - started) * 1000.0
        meta = ExtractionMeta(
            extractor=self.extractor_id,
            model_id=self._model_id,
            prompt_version=PROMPT_V1,
            tokens_in=total_tokens_in,
            tokens_out=total_tokens_out,
            cost_usd=total_cost if total_cost > 0 else None,
            latency_ms=latency_ms,
            cache_hit=False,
        )
        merged = merge_extractions(circular.circular_id, chunk_results, meta)

        # Cache the T0-independent (absolute-epoch) extraction; put() serializes
        # immediately, so the relative resolution below doesn't leak into cache.
        if self._cache is not None:
            self._cache.put(
                extractor_id=self.extractor_id,
                model_id=self._model_id,
                prompt_version=PROMPT_V1,
                circular_id=circular.circular_id,
                body_sha1=body_hash,
                extraction=merged,
                tokens_in=total_tokens_in,
                tokens_out=total_tokens_out,
                cost_usd=meta.cost_usd,
                latency_ms=latency_ms,
            )

        resolve_relative_epochs(merged, circular.trigger_time)
        return merged

    # ---- internal ----

    def _call_api(self, circular: Circular) -> tuple[dict[str, Any], Any]:
        """One Anthropic call. Returns (tool input dict, response.usage)."""
        system_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": build_system_text(),
                "cache_control": {"type": "ephemeral"},
            }
        ]
        tools: list[dict[str, Any]] = [
            {
                "name": "submit_extraction",
                "description": "Submit the structured extraction from this circular.",
                "input_schema": llm_input_schema(),
                "cache_control": {"type": "ephemeral"},
            }
        ]
        messages = build_messages(circular)

        # Anthropic SDK uses very strict TypedDicts; our schema-derived dicts are
        # structurally equivalent but mypy can't prove it. Cast to Any for the call.
        response = self._client.messages.create(  # type: ignore[call-overload]
            model=self._model_id,
            max_tokens=self._max_tokens,
            system=system_blocks,
            tools=tools,
            tool_choice={"type": "tool", "name": "submit_extraction"},
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
        )

        tool_input = self._extract_tool_input(response.content)
        return tool_input, response.usage

    @staticmethod
    def _extract_tool_input(content: Iterable[Any]) -> dict[str, Any]:
        def _attr_or_key(block: Any, name: str) -> Any:
            # `or` short-circuit would skip an empty-but-valid dict; use explicit None check.
            value = getattr(block, name, None)
            if value is None and isinstance(block, dict):
                value = block.get(name)
            return value

        for block in content:
            if (
                _attr_or_key(block, "type") == "tool_use"
                and _attr_or_key(block, "name") == "submit_extraction"
            ):
                tool_input = _attr_or_key(block, "input")
                if isinstance(tool_input, dict):
                    return tool_input
        raise ValueError("Claude response did not contain a submit_extraction tool_use block")
