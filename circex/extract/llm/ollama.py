"""OllamaExtractor — JSON-mode constrained extraction with one repair retry.

Mistral-7B-Instruct-v0.2 doesn't have first-class tool use. We use `format="json"`
and pass the input schema in the prompt. On Pydantic validation failure, retry
once with the validation error appended to the messages.

Cost is always None (open-source local model). Latency is wall-clock.
"""

from __future__ import annotations

import json
import time
from typing import Any

import ollama
import structlog
from pydantic import ValidationError

from circex.cache.llm import LLMCache, cache_key
from circex.extract.llm.chunker import chunk_body, merge_extractions
from circex.extract.llm.prompt import (
    PROMPT_V1,
    build_messages,
    build_system_text,
    llm_input_schema,
)
from circex.extract.protocol import Circular, Extractor
from circex.schema import CircularExtraction, ExtractionMeta

log = structlog.get_logger(__name__)

DEFAULT_OLLAMA_MODEL = "mistral:7b-instruct-v0.2"


class OllamaExtractor(Extractor):
    """LLM extractor backed by a local Ollama model."""

    def __init__(
        self,
        model_id: str = DEFAULT_OLLAMA_MODEL,
        cache: LLMCache | None = None,
        client: Any | None = None,
    ) -> None:
        self._model_id = model_id
        self._cache = cache
        self._client = client or ollama

    @property
    def extractor_id(self) -> str:
        return f"ollama:{self._model_id}"

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
                return cached.extraction.model_copy(update={"extraction_meta": meta})

        chunks = chunk_body(circular.body)

        started = time.perf_counter()
        chunk_results: list[CircularExtraction] = []

        for chunk in chunks:
            payload = self._call_with_repair(
                Circular(
                    circular_id=circular.circular_id,
                    subject=circular.subject,
                    body=chunk,
                    event_id=circular.event_id,
                )
            )
            payload["circular_id"] = circular.circular_id
            payload.setdefault(
                "extraction_meta",
                {"extractor": self.extractor_id, "model_id": self._model_id},
            )
            chunk_results.append(CircularExtraction.model_validate(payload))

        latency_ms = (time.perf_counter() - started) * 1000.0
        meta = ExtractionMeta(
            extractor=self.extractor_id,
            model_id=self._model_id,
            prompt_version=PROMPT_V1,
            tokens_in=None,
            tokens_out=None,
            cost_usd=None,
            latency_ms=latency_ms,
            cache_hit=False,
        )
        merged = merge_extractions(circular.circular_id, chunk_results, meta)

        if self._cache is not None:
            self._cache.put(
                extractor_id=self.extractor_id,
                model_id=self._model_id,
                prompt_version=PROMPT_V1,
                circular_id=circular.circular_id,
                body_sha1=body_hash,
                extraction=merged,
                latency_ms=latency_ms,
            )

        return merged

    # ---- internal ----

    def _system_text_with_schema(self) -> str:
        """Ollama lacks tool-use; we embed the schema in the system message."""
        schema_json = json.dumps(llm_input_schema(), indent=2)
        return (
            build_system_text()
            + "\n\nReturn a JSON object conforming to this schema:\n"
            + schema_json
        )

    def _call_with_repair(self, circular: Circular) -> dict[str, Any]:
        """Call once; on validation error, retry once with the error appended."""
        system_text = self._system_text_with_schema()
        messages = [
            {"role": "system", "content": system_text},
            *build_messages(circular),
        ]

        first = self._client.chat(
            model=self._model_id, messages=messages, format="json"
        )
        first_content = first["message"]["content"]
        try:
            return self._parse_and_strip_meta(first_content)
        except (ValidationError, json.JSONDecodeError) as exc:
            error_message = str(exc)
            log.warning("ollama_repair_retry", error=error_message)

        # Repair retry: append the error and ask for a corrected JSON.
        messages.append({"role": "assistant", "content": first_content})
        messages.append(
            {
                "role": "user",
                "content": (
                    "The previous response failed schema validation with: "
                    f"{error_message}. Emit a corrected JSON object only."
                ),
            }
        )
        second = self._client.chat(
            model=self._model_id, messages=messages, format="json"
        )
        return self._parse_and_strip_meta(second["message"]["content"])

    @staticmethod
    def _parse_and_strip_meta(content: str) -> dict[str, Any]:
        """Parse JSON and validate against the input schema by trial-constructing."""
        loaded = json.loads(content)
        if not isinstance(loaded, dict):
            raise json.JSONDecodeError("expected JSON object, got non-dict", content, 0)
        payload: dict[str, Any] = dict(loaded)
        trial = dict(payload)
        trial.setdefault("circular_id", 0)
        trial.setdefault("extraction_meta", {"extractor": "trial"})
        CircularExtraction.model_validate(trial)
        payload.pop("extraction_meta", None)
        return payload
