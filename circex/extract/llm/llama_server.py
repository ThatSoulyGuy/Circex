"""LlamaServerExtractor — Mistral-7B via a llama.cpp OpenAI-compatible server.

Where the Ollama path uses loose JSON mode + a repair retry + fail-soft (Mistral
regularly emits schema-non-conforming JSON), a llama.cpp server enforces the
output schema *at decode time* via grammar-constrained decoding
(`response_format: {type: json_schema}`) — the model cannot emit non-conforming
JSON, so no repair loop is needed. Same shared prompt and `llm_input_schema()` as
the other backends, so eval numbers stay comparable.

Set up on MSI `agc03:8080` (co-located with BOOM), which makes it both the box for
the full LLM eval and the production LLM backend for the SkyPortal service — the
service calls `localhost:8080`, no network hop. Point at it with `CIRCEX_LLAMA_URL`.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import requests
import structlog
from pydantic import ValidationError

from circex.cache.llm import LLMCache, cache_key
from circex.extract.llm.chunker import chunk_body, merge_extractions
from circex.extract.llm.ollama import OllamaExtractor  # reuse the parse/sanitize helpers
from circex.extract.llm.prompt import (
    PROMPT_V1,
    build_messages,
    build_system_text,
    llm_grammar_schema,
)
from circex.extract.protocol import Circular, Extractor
from circex.extract.timing import resolve_observation_epoch, resolve_relative_epochs
from circex.schema import CircularExtraction, ExtractionMeta

log = structlog.get_logger(__name__)

DEFAULT_LLAMA_URL = os.environ.get("CIRCEX_LLAMA_URL", "http://localhost:8080")
DEFAULT_LLAMA_MODEL = os.environ.get("CIRCEX_LLAMA_MODEL", "mistral-7b")
# Grammar-constrained decoding on the full CircularExtraction schema is far slower
# than free generation on a dense circular; give it room. Override for tuning.
DEFAULT_LLAMA_TIMEOUT = float(os.environ.get("CIRCEX_LLAMA_TIMEOUT", "300"))
# Hard cap on generated tokens. Belt-and-braces with the schema's maxItems: even a
# looping model stops here instead of grinding out 10k tokens under constrained
# sampling. A rich extraction fits comfortably in this budget.
DEFAULT_LLAMA_MAX_TOKENS = int(os.environ.get("CIRCEX_LLAMA_MAX_TOKENS", "2048"))


class LlamaServerExtractor(Extractor):
    """Grammar-constrained extraction against a llama.cpp OpenAI-compatible server."""

    def __init__(
        self,
        base_url: str = DEFAULT_LLAMA_URL,
        model_id: str = DEFAULT_LLAMA_MODEL,
        cache: LLMCache | None = None,
        timeout: float = DEFAULT_LLAMA_TIMEOUT,
        session: Any | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        self._cache = cache
        self._timeout = timeout
        self._session = session or requests  # injectable for tests

    @property
    def extractor_id(self) -> str:
        return f"llama-server:{self._model_id}"

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
                resolve_relative_epochs(result, circular.trigger_time)
                resolve_observation_epoch(result, circular.body)
                return result

        started = time.perf_counter()
        chunk_results: list[CircularExtraction] = []
        had_error = False
        for chunk in chunk_body(circular.body):
            try:
                payload = self._call(
                    Circular(
                        circular_id=circular.circular_id,
                        subject=circular.subject,
                        body=chunk,
                        event_id=circular.event_id,
                    )
                )
            except (ValidationError, json.JSONDecodeError, requests.RequestException) as exc:
                # Grammar-constrained output shouldn't fail validation, but a
                # server/transport error still shouldn't crash the run.
                log.warning(
                    "llama_server_extract_failed",
                    circular_id=circular.circular_id,
                    error=str(exc)[:300],
                )
                payload = {}
                had_error = True
            payload["circular_id"] = circular.circular_id
            llm_notes = payload.pop("_llm_notes", [])
            if not isinstance(llm_notes, list):
                llm_notes = []
            payload["extraction_meta"] = {
                "extractor": self.extractor_id,
                "model_id": self._model_id,
                "notes": llm_notes,
            }
            chunk_results.append(CircularExtraction.model_validate(payload))

        latency_ms = (time.perf_counter() - started) * 1000.0
        meta = ExtractionMeta(
            extractor=self.extractor_id,
            model_id=self._model_id,
            prompt_version=PROMPT_V1,
            latency_ms=latency_ms,
            cache_hit=False,
        )
        merged = merge_extractions(circular.circular_id, chunk_results, meta)
        # Never cache a partial/empty result produced by a transport failure — a
        # tunnel blip would otherwise poison the cache and be silently skipped on
        # re-run. Only persist extractions where every chunk actually returned.
        if self._cache is not None and not had_error:
            self._cache.put(
                extractor_id=self.extractor_id,
                model_id=self._model_id,
                prompt_version=PROMPT_V1,
                circular_id=circular.circular_id,
                body_sha1=body_hash,
                extraction=merged,
                latency_ms=latency_ms,
            )
        resolve_relative_epochs(merged, circular.trigger_time)
        # Bind a single body-level observation datetime to untimed rows, so a
        # table without its own date column still gets an obs_mjd (as regex does).
        resolve_observation_epoch(merged, circular.body)
        return merged

    def _call(self, circular: Circular) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": build_system_text()},
            *build_messages(circular),
        ]
        resp = self._session.post(
            f"{self._base_url}/v1/chat/completions",
            json={
                "model": self._model_id,
                "messages": messages,
                "temperature": 0,
                "max_tokens": DEFAULT_LLAMA_MAX_TOKENS,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "circular_extraction",
                        "schema": llm_grammar_schema(),  # lean: scored fields only
                    },
                },
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        payload = OllamaExtractor._parse_and_strip_meta(content)
        return OllamaExtractor._sanitize_payload(payload, body=circular.body)
