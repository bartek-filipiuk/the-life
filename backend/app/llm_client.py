"""OpenRouter LLM client using the OpenAI SDK.

Provides two-phase calling for the AI cycle engine:
1. Decision phase — tool calling, structured JSON output
2. Creation phase — room content generation

Security: API key validated before calls, timeouts enforced, rate limit backoff.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI, APITimeoutError, RateLimitError

logger = logging.getLogger(__name__)

# Mask API key in logs — show only last 4 chars
_MASKED = "***"


@dataclass
class LLMUsage:
    """Token and cost tracking for a single LLM call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""
    duration_ms: int = 0


@dataclass
class LLMResponse:
    """Wrapper for an LLM response with parsed content and usage."""

    content: str = ""
    parsed_json: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)
    raw_response: Any = None


class LLMClient:
    """Async OpenRouter client with retry and cost tracking."""

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-5.4",
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise ValueError("OpenRouter API key is required")

        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )
        logger.info("LLM client initialized for model=%s (key=%s)", model, _MASKED)

    async def decision_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.8,
    ) -> LLMResponse:
        """Decision phase: call LLM with tool definitions, expect structured JSON.

        Args:
            messages: Chat messages (system + user).
            tools: OpenAI-format tool definitions.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with parsed_json and/or tool_calls.
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        if tools:
            kwargs["tools"] = tools
            kwargs.pop("response_format", None)  # can't use both

        return await self._call_with_retry(**kwargs)

    async def creation_call(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.9,
    ) -> LLMResponse:
        """Creation phase: call LLM for room content generation.

        Args:
            messages: Chat messages with context from decision phase.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with content (and optionally parsed_json).
        """
        return await self._call_with_retry(
            model=self._model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

    async def _call_with_retry(self, **kwargs: Any) -> LLMResponse:
        """Execute LLM call with exponential backoff on rate limits."""
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                start = time.monotonic()
                response = await self._client.chat.completions.create(**kwargs)
                duration_ms = int((time.monotonic() - start) * 1000)

                return self._parse_response(response, duration_ms)

            except RateLimitError as e:
                last_error = e
                wait = 2 ** attempt * 2  # 2, 4, 8 seconds
                logger.warning("Rate limited (attempt %d/%d), waiting %ds", attempt + 1, self._max_retries, wait)
                import asyncio
                await asyncio.sleep(wait)

            except APITimeoutError as e:
                last_error = e
                logger.warning("Timeout (attempt %d/%d)", attempt + 1, self._max_retries)
                if attempt < self._max_retries - 1:
                    import asyncio
                    await asyncio.sleep(1)

        raise RuntimeError(f"LLM call failed after {self._max_retries} retries: {last_error}")

    def _parse_response(self, response: Any, duration_ms: int) -> LLMResponse:
        """Parse OpenAI-format response into LLMResponse."""
        choice = response.choices[0] if response.choices else None
        message = choice.message if choice else None

        # Extract content
        content = message.content or "" if message else ""

        # Try to parse JSON
        parsed_json: dict[str, Any] | None = None
        if content:
            try:
                parsed_json = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                pass

        # Extract tool calls
        tool_calls: list[dict[str, Any]] = []
        if message and message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments) if tc.function.arguments else {},
                })

        # Usage tracking
        usage = LLMUsage(
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
            total_tokens=response.usage.total_tokens if response.usage else 0,
            model=response.model or self._model,
            duration_ms=duration_ms,
        )

        return LLMResponse(
            content=content,
            parsed_json=parsed_json,
            tool_calls=tool_calls,
            usage=usage,
            raw_response=response,
        )
