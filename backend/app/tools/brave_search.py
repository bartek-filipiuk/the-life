"""Brave Search provider implementation.

Wraps the Brave Search API behind the SearchProvider interface.
Security: query sanitized, response validated, timeout enforced.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.tools.search_provider import (
    SearchAuthError,
    SearchProviderError,
    SearchQuery,
    SearchRateLimitError,
    SearchResponse,
    SearchResult,
    SearchTimeoutError,
)

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
MAX_QUERY_LENGTH = 400
COST_PER_QUERY = 0.005  # approximate USD


class BraveSearchProvider:
    """Brave Search API provider."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("Brave Search API key is required")
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "brave"

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Search via Brave API."""
        q = query.query.strip()
        if not q:
            raise ValueError("Search query cannot be empty")
        if len(q) > MAX_QUERY_LENGTH:
            q = q[:MAX_QUERY_LENGTH]

        count = min(max(1, query.max_results), 20)
        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=query.timeout) as client:
                response = await client.get(
                    BRAVE_SEARCH_URL,
                    params={"q": q, "count": count},
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip",
                        "X-Subscription-Token": self._api_key,
                    },
                )
        except httpx.TimeoutException as e:
            raise SearchTimeoutError(f"Brave search timed out after {query.timeout}s") from e

        elapsed_ms = (time.monotonic() - start) * 1000

        if response.status_code == 401:
            raise SearchAuthError("Invalid Brave API key")
        if response.status_code == 429:
            raise SearchRateLimitError("Brave rate limit exceeded")
        if response.status_code >= 400:
            raise SearchProviderError(f"Brave API error: {response.status_code}")

        data = response.json()
        results = _parse_results(data)

        return SearchResponse(
            results=results,
            provider="brave",
            cost_usd=COST_PER_QUERY,
            response_time_ms=elapsed_ms,
        )


def _parse_results(data: dict[str, Any]) -> list[SearchResult]:
    """Parse Brave response into normalized SearchResult list."""
    results: list[SearchResult] = []
    for item in data.get("web", {}).get("results", []):
        url = item.get("url", "")
        if url:
            results.append(SearchResult(
                title=item.get("title", ""),
                url=url,
                snippet=item.get("description", ""),
            ))
    return results
