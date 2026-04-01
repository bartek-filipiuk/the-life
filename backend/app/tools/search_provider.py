"""Abstract search provider interface.

All search backends (Brave, Tavily, etc.) implement this protocol.
The cycle engine uses only this interface — never a concrete provider directly.

See docs/adding-tools.md for how to add new search providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SearchQuery:
    """Normalized search query — provider-agnostic."""

    query: str
    max_results: int = 5
    timeout: float = 10.0


@dataclass(frozen=True)
class SearchResult:
    """A single search result — normalized across providers."""

    title: str
    url: str
    snippet: str
    relevance_score: float | None = None  # 0.0-1.0, only some providers


@dataclass(frozen=True)
class SearchResponse:
    """Full search response — normalized across providers."""

    results: list[SearchResult]
    provider: str  # "brave", "tavily", etc.
    answer: str | None = None  # LLM-generated summary (Tavily only)
    cost_usd: float = 0.0
    response_time_ms: float = 0.0


# ── Exceptions ─────────────────────────────────────────────────────────


class SearchProviderError(Exception):
    """Base exception for all search provider errors."""


class SearchAuthError(SearchProviderError):
    """API key invalid or missing."""


class SearchRateLimitError(SearchProviderError):
    """Rate limit exceeded."""


class SearchTimeoutError(SearchProviderError):
    """Request timed out."""


class SearchQuotaExhaustedError(SearchProviderError):
    """Plan credits / quota exhausted."""


# ── Protocol ───────────────────────────────────────────────────────────


@runtime_checkable
class SearchProvider(Protocol):
    """Interface that all search backends must implement."""

    @property
    def name(self) -> str:
        """Provider name (e.g., 'brave', 'tavily')."""
        ...

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute a search query and return normalized results.

        Raises:
            SearchAuthError: If API key is invalid.
            SearchRateLimitError: If rate limit exceeded.
            SearchTimeoutError: If request times out.
            SearchQuotaExhaustedError: If credits exhausted.
            SearchProviderError: On other provider errors.
        """
        ...
