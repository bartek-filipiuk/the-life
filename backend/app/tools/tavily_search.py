"""Tavily Search provider implementation.

Wraps the Tavily Search API behind the SearchProvider interface.
Uses the tavily-python SDK (AsyncTavilyClient) for async support.
Provides LLM-optimized results with relevance scores and optional AI answers.

Security: query sanitized, timeout enforced, API key validated.
"""

from __future__ import annotations

import logging
import time

from app.tools.search_provider import (
    SearchAuthError,
    SearchProviderError,
    SearchQuery,
    SearchQuotaExhaustedError,
    SearchRateLimitError,
    SearchResponse,
    SearchResult,
    SearchTimeoutError,
)

logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 400
COST_PER_BASIC_QUERY = 0.008  # 1 credit
COST_PER_ADVANCED_QUERY = 0.016  # 2 credits


class TavilySearchProvider:
    """Tavily Search API provider with LLM-optimized results."""

    def __init__(
        self,
        api_key: str,
        search_depth: str = "basic",
        include_answer: bool = False,
    ) -> None:
        if not api_key:
            raise ValueError("Tavily API key is required")
        self._api_key = api_key
        self._search_depth = search_depth
        self._include_answer = include_answer

    @property
    def name(self) -> str:
        return "tavily"

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Search via Tavily API using AsyncTavilyClient."""
        try:
            from tavily import AsyncTavilyClient
        except ImportError:
            raise SearchProviderError(
                "tavily-python not installed. Run: pip install tavily-python"
            )

        q = query.query.strip()
        if not q:
            raise ValueError("Search query cannot be empty")
        if len(q) > MAX_QUERY_LENGTH:
            q = q[:MAX_QUERY_LENGTH]

        count = min(max(1, query.max_results), 20)
        start = time.monotonic()

        try:
            client = AsyncTavilyClient(api_key=self._api_key)
            response = await client.search(
                query=q,
                search_depth=self._search_depth,
                max_results=count,
                include_answer=self._include_answer,
                timeout=int(query.timeout),
            )
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            error_str = str(e).lower()

            if "api key" in error_str or "invalid" in error_str or "401" in error_str:
                raise SearchAuthError("Invalid Tavily API key") from e
            if "429" in error_str or "rate" in error_str:
                raise SearchRateLimitError("Tavily rate limit exceeded") from e
            if "432" in error_str or "433" in error_str or "credit" in error_str or "limit" in error_str:
                raise SearchQuotaExhaustedError("Tavily credits exhausted") from e
            if "timeout" in error_str:
                raise SearchTimeoutError(f"Tavily search timed out after {query.timeout}s") from e

            raise SearchProviderError(f"Tavily search failed: {e}") from e

        elapsed_ms = (time.monotonic() - start) * 1000

        results: list[SearchResult] = []
        for item in response.get("results", []):
            url = item.get("url", "")
            if url:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=url,
                    snippet=item.get("content", ""),
                    relevance_score=item.get("score"),
                ))

        cost = COST_PER_ADVANCED_QUERY if self._search_depth == "advanced" else COST_PER_BASIC_QUERY

        return SearchResponse(
            results=results,
            provider="tavily",
            answer=response.get("answer"),
            cost_usd=cost,
            response_time_ms=elapsed_ms,
        )
