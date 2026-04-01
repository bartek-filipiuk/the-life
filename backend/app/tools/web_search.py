"""Brave Search API wrapper.

Security: query input sanitized, response validated, 10s timeout.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
MAX_QUERY_LENGTH = 400
DEFAULT_TIMEOUT = 10.0
DEFAULT_COUNT = 5


@dataclass(frozen=True)
class SearchResult:
    """A single web search result."""

    title: str
    url: str
    snippet: str


async def search(
    query: str,
    api_key: str,
    count: int = DEFAULT_COUNT,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[SearchResult]:
    """Search the web using Brave Search API.

    Args:
        query: Search query string (max 400 chars).
        api_key: Brave Search API key.
        count: Number of results (max 20).
        timeout: Request timeout in seconds.

    Returns:
        List of SearchResult objects.

    Raises:
        ValueError: If query is empty or too long.
        httpx.HTTPStatusError: On API errors.
    """
    # Sanitize input
    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty")
    if len(query) > MAX_QUERY_LENGTH:
        query = query[:MAX_QUERY_LENGTH]
        logger.warning("Query truncated to %d chars", MAX_QUERY_LENGTH)

    count = min(max(1, count), 20)

    if not api_key:
        raise ValueError("Brave Search API key is required")

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            BRAVE_SEARCH_URL,
            params={"q": query, "count": count},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
        )
        response.raise_for_status()

    data = response.json()
    return _parse_results(data)


def _parse_results(data: dict[str, Any]) -> list[SearchResult]:
    """Parse Brave Search API response into SearchResult list."""
    results: list[SearchResult] = []

    web_results = data.get("web", {}).get("results", [])
    for item in web_results:
        title = item.get("title", "")
        url = item.get("url", "")
        snippet = item.get("description", "")

        if url:  # skip results without URL
            results.append(SearchResult(title=title, url=url, snippet=snippet))

    return results
