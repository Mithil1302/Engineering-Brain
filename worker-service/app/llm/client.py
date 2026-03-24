"""
Production-grade Google Gemini LLM client for KA-CHOW.

Features:
  - Retry with exponential backoff + jitter (3 attempts)
  - In-memory LRU response cache (TTL-based)
  - Structured JSON output mode
  - Streaming support for long-form generation
  - Token usage tracking via logging
  - Circuit breaker to prevent cascade failures
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional

from google import genai
from google.genai import types

log = logging.getLogger("ka-chow.llm")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    """Wrapper around a single LLM generation result."""
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cached: bool = False
    finish_reason: str = ""

    def as_json(self) -> Any:
        """Parse the text as JSON; returns raw text on failure."""
        try:
            return json.loads(self.text)
        except (json.JSONDecodeError, TypeError):
            return self.text


@dataclass
class _CacheEntry:
    response: LLMResponse
    created_at: float


@dataclass
class _CircuitState:
    failures: int = 0
    open_until: float = 0.0
    half_open_attempt: bool = False


# ---------------------------------------------------------------------------
# Core client
# ---------------------------------------------------------------------------

class LLMClient:
    """
    Thread-safe Gemini client with caching, retries, and circuit breaker.

    Instantiate via the singleton in ``app.llm.get_llm_client()``.
    """

    # -- construction -------------------------------------------------------
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-2.0-flash",
        temperature: float = 0.3,
        max_output_tokens: int = 8192,
        max_retries: int = 3,
        cache_maxsize: int = 256,
        cache_ttl_sec: float = 300.0,
        circuit_failure_threshold: int = 5,
        circuit_cooldown_sec: float = 60.0,
    ):
        self._api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.max_retries = max_retries

        # Gemini SDK client
        self._client = genai.Client(api_key=api_key) if api_key else None

        # LRU cache --------------------------------------------------------
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._cache_maxsize = cache_maxsize
        self._cache_ttl = cache_ttl_sec
        self._cache_lock = threading.Lock()

        # Circuit breaker ---------------------------------------------------
        self._circuit = _CircuitState()
        self._circuit_threshold = circuit_failure_threshold
        self._circuit_cooldown = circuit_cooldown_sec
        self._circuit_lock = threading.Lock()

        # Telemetry ---------------------------------------------------------
        self._total_requests = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    # -- public interface ---------------------------------------------------

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        json_mode: bool = False,
        json_schema: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
    ) -> LLMResponse:
        """
        Synchronous text generation with automatic retry.

        Parameters
        ----------
        prompt : str
            The user-facing prompt.
        system_prompt : str, optional
            System instruction preamble.
        temperature : float, optional
            Override instance default.
        max_output_tokens : int, optional
            Override instance default.
        json_mode : bool
            If True, instruct Gemini to return valid JSON.
        json_schema : dict, optional
            If provided (with json_mode=True), constrains output to this schema.
        use_cache : bool
            Whether to check / populate the response cache.
        """
        if not self._client:
            raise RuntimeError(
                "LLM client is not configured. Set GEMINI_API_KEY environment variable."
            )

        self._check_circuit()

        # --- cache lookup --------------------------------------------------
        cache_key = self._cache_key(prompt, system_prompt, temperature, json_mode)
        if use_cache:
            cached = self._cache_get(cache_key)
            if cached is not None:
                cached.cached = True
                return cached

        # --- build config --------------------------------------------------
        temp = temperature if temperature is not None else self.temperature
        max_tok = max_output_tokens if max_output_tokens is not None else self.max_output_tokens

        gen_config_kwargs: Dict[str, Any] = {
            "temperature": temp,
            "max_output_tokens": max_tok,
        }
        if json_mode:
            gen_config_kwargs["response_mime_type"] = "application/json"
            if json_schema:
                gen_config_kwargs["response_schema"] = json_schema

        config = types.GenerateContentConfig(
            system_instruction=system_prompt or None,
            **gen_config_kwargs,
        )

        # --- retry loop ----------------------------------------------------
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                t0 = time.monotonic()
                response = self._client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                elapsed_ms = (time.monotonic() - t0) * 1000

                text = response.text or ""
                input_tokens = getattr(
                    getattr(response, "usage_metadata", None), "prompt_token_count", 0
                ) or 0
                output_tokens = getattr(
                    getattr(response, "usage_metadata", None), "candidates_token_count", 0
                ) or 0

                result = LLMResponse(
                    text=text,
                    model=self.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=round(elapsed_ms, 1),
                    cached=False,
                    finish_reason=str(
                        getattr(
                            (response.candidates[0] if response.candidates else None),
                            "finish_reason",
                            "unknown",
                        )
                    ),
                )

                self._record_success()
                self._telemetry(result)

                if use_cache:
                    self._cache_put(cache_key, result)

                return result

            except Exception as exc:
                last_exc = exc
                log.warning(
                    "LLM call attempt %d/%d failed: %s",
                    attempt, self.max_retries, exc,
                )
                self._record_failure()
                if attempt < self.max_retries:
                    self._backoff_sleep(attempt)

        raise RuntimeError(
            f"LLM call failed after {self.max_retries} attempts: {last_exc}"
        ) from last_exc

    def generate_json(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
        use_cache: bool = True,
    ) -> Any:
        """
        Generate and parse JSON output in one call.
        Returns the parsed Python object (dict / list / str / number).
        """
        resp = self.generate(
            prompt,
            system_prompt=system_prompt,
            json_mode=True,
            json_schema=json_schema,
            temperature=temperature,
            use_cache=use_cache,
        )
        return resp.as_json()

    def generate_streaming(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
    ) -> Generator[str, None, None]:
        """Yield text chunks as they arrive from the model."""
        if not self._client:
            raise RuntimeError(
                "LLM client is not configured. Set GEMINI_API_KEY environment variable."
            )

        self._check_circuit()

        temp = temperature if temperature is not None else self.temperature
        max_tok = max_output_tokens if max_output_tokens is not None else self.max_output_tokens

        config = types.GenerateContentConfig(
            system_instruction=system_prompt or None,
            temperature=temp,
            max_output_tokens=max_tok,
        )

        try:
            stream = self._client.models.generate_content_stream(
                model=self.model,
                contents=prompt,
                config=config,
            )
            for chunk in stream:
                if chunk.text:
                    yield chunk.text
            self._record_success()
        except Exception as exc:
            self._record_failure()
            raise RuntimeError(f"LLM streaming failed: {exc}") from exc

    def multi_turn(
        self,
        messages: List[Dict[str, str]],
        *,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        """
        Multi-turn conversation.

        messages : list of {"role": "user"|"model", "content": "..."}
        """
        if not self._client:
            raise RuntimeError("LLM client is not configured.")

        self._check_circuit()

        temp = temperature if temperature is not None else self.temperature
        gen_config: Dict[str, Any] = {
            "temperature": temp,
            "max_output_tokens": self.max_output_tokens,
        }
        if json_mode:
            gen_config["response_mime_type"] = "application/json"

        config = types.GenerateContentConfig(
            system_instruction=system_prompt or None,
            **gen_config,
        )

        # Build content list for Gemini
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            gemini_role = "model" if role in ("model", "assistant") else "user"
            contents.append(
                types.Content(
                    role=gemini_role,
                    parts=[types.Part.from_text(text=msg["content"])],
                )
            )

        try:
            t0 = time.monotonic()
            response = self._client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
            elapsed_ms = (time.monotonic() - t0) * 1000

            text = response.text or ""
            input_tokens = getattr(
                getattr(response, "usage_metadata", None), "prompt_token_count", 0
            ) or 0
            output_tokens = getattr(
                getattr(response, "usage_metadata", None), "candidates_token_count", 0
            ) or 0

            result = LLMResponse(
                text=text,
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=round(elapsed_ms, 1),
                finish_reason=str(
                    getattr(
                        (response.candidates[0] if response.candidates else None),
                        "finish_reason",
                        "unknown",
                    )
                ),
            )
            self._record_success()
            self._telemetry(result)
            return result
        except Exception as exc:
            self._record_failure()
            raise RuntimeError(f"Multi-turn LLM call failed: {exc}") from exc

    # -- health check -------------------------------------------------------

    def health(self) -> Dict[str, Any]:
        """Return client health stats."""
        return {
            "configured": self._client is not None,
            "model": self.model,
            "total_requests": self._total_requests,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "cache_size": len(self._cache),
            "circuit_open": self._circuit.open_until > time.time(),
            "circuit_failures": self._circuit.failures,
        }

    # -- internal -----------------------------------------------------------

    @staticmethod
    def _cache_key(
        prompt: str,
        system_prompt: Optional[str],
        temperature: Optional[float],
        json_mode: bool,
    ) -> str:
        raw = f"{system_prompt or ''}||{prompt}||{temperature}||{json_mode}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> Optional[LLMResponse]:
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if (time.time() - entry.created_at) > self._cache_ttl:
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            return entry.response

    def _cache_put(self, key: str, response: LLMResponse) -> None:
        with self._cache_lock:
            self._cache[key] = _CacheEntry(response=response, created_at=time.time())
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_maxsize:
                self._cache.popitem(last=False)

    def _check_circuit(self) -> None:
        with self._circuit_lock:
            if self._circuit.open_until > time.time():
                raise RuntimeError(
                    "LLM circuit breaker is open — too many recent failures. "
                    f"Retry after {int(self._circuit.open_until - time.time())}s."
                )

    def _record_success(self) -> None:
        with self._circuit_lock:
            self._circuit.failures = 0
            self._circuit.open_until = 0.0

    def _record_failure(self) -> None:
        with self._circuit_lock:
            self._circuit.failures += 1
            if self._circuit.failures >= self._circuit_threshold:
                self._circuit.open_until = time.time() + self._circuit_cooldown
                log.error(
                    "LLM circuit breaker OPENED after %d failures; cooldown %ds",
                    self._circuit.failures,
                    self._circuit_cooldown,
                )

    @staticmethod
    def _backoff_sleep(attempt: int) -> None:
        import random
        delay = min(30, (2 ** attempt) + random.uniform(0, 1))
        time.sleep(delay)

    def _telemetry(self, r: LLMResponse) -> None:
        self._total_requests += 1
        self._total_input_tokens += r.input_tokens
        self._total_output_tokens += r.output_tokens
        log.info(
            "LLM [%s] in=%d out=%d latency=%.0fms cached=%s",
            r.model, r.input_tokens, r.output_tokens, r.latency_ms, r.cached,
        )
