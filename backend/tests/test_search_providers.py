"""Tests for search provider interface, Brave, Tavily, and factory."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.tools.brave_search import BraveSearchProvider
from app.tools.search_factory import create_search_provider
from app.tools.search_provider import (
    SearchAuthError,
    SearchProvider,
    SearchProviderError,
    SearchQuery,
    SearchRateLimitError,
    SearchTimeoutError,
)


# ── SearchProvider Protocol ────────────────────────────────────────────


class TestProtocol:
    def test_brave_is_search_provider(self):
        p = BraveSearchProvider(api_key="test")
        assert isinstance(p, SearchProvider)

    def test_brave_name(self):
        p = BraveSearchProvider(api_key="test")
        assert p.name == "brave"


# ── Brave Provider ─────────────────────────────────────────────────────


class TestBraveProvider:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        provider = BraveSearchProvider(api_key="test-key")
        mock_response = httpx.Response(
            200,
            json={"web": {"results": [
                {"title": "R1", "url": "https://example.com/1", "description": "Snippet 1"},
                {"title": "R2", "url": "https://example.com/2", "description": "Snippet 2"},
            ]}},
            request=httpx.Request("GET", "https://test"),
        )

        with patch("app.tools.brave_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_cls.return_value)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.get = AsyncMock(return_value=mock_response)

            result = await provider.search(SearchQuery(query="test"))

        assert result.provider == "brave"
        assert len(result.results) == 2
        assert result.results[0].title == "R1"
        assert result.cost_usd > 0

    @pytest.mark.asyncio
    async def test_empty_query_raises(self):
        provider = BraveSearchProvider(api_key="test")
        with pytest.raises(ValueError, match="empty"):
            await provider.search(SearchQuery(query=""))

    def test_missing_key_raises(self):
        with pytest.raises(ValueError, match="required"):
            BraveSearchProvider(api_key="")

    @pytest.mark.asyncio
    async def test_timeout_raises_search_error(self):
        provider = BraveSearchProvider(api_key="test")
        with patch("app.tools.brave_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_cls.return_value)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

            with pytest.raises(SearchTimeoutError):
                await provider.search(SearchQuery(query="test"))

    @pytest.mark.asyncio
    async def test_401_raises_auth_error(self):
        provider = BraveSearchProvider(api_key="bad-key")
        mock_response = httpx.Response(401, request=httpx.Request("GET", "https://test"))

        with patch("app.tools.brave_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_cls.return_value)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.get = AsyncMock(return_value=mock_response)

            with pytest.raises(SearchAuthError):
                await provider.search(SearchQuery(query="test"))

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit(self):
        provider = BraveSearchProvider(api_key="test")
        mock_response = httpx.Response(429, request=httpx.Request("GET", "https://test"))

        with patch("app.tools.brave_search.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_cls.return_value)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value.get = AsyncMock(return_value=mock_response)

            with pytest.raises(SearchRateLimitError):
                await provider.search(SearchQuery(query="test"))


# ── Tavily Provider ────────────────────────────────────────────────────


class TestTavilyProvider:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        from app.tools.tavily_search import TavilySearchProvider
        provider = TavilySearchProvider(api_key="tvly-test")

        mock_response = {
            "results": [
                {"title": "T1", "url": "https://example.com/1", "content": "Content 1", "score": 0.95},
                {"title": "T2", "url": "https://example.com/2", "content": "Content 2", "score": 0.80},
            ],
            "answer": "AI-generated summary",
        }

        # Tavily uses lazy import inside search(), so we patch the module it imports from
        mock_client_instance = MagicMock()
        mock_client_instance.search = AsyncMock(return_value=mock_response)

        with patch.dict("sys.modules", {"tavily": MagicMock(AsyncTavilyClient=MagicMock(return_value=mock_client_instance))}):
            result = await provider.search(SearchQuery(query="test"))

        assert result.provider == "tavily"
        assert len(result.results) == 2
        assert result.results[0].relevance_score == 0.95
        assert result.answer == "AI-generated summary"

    def test_missing_key_raises(self):
        from app.tools.tavily_search import TavilySearchProvider
        with pytest.raises(ValueError, match="required"):
            TavilySearchProvider(api_key="")

    @pytest.mark.asyncio
    async def test_name(self):
        from app.tools.tavily_search import TavilySearchProvider
        p = TavilySearchProvider(api_key="tvly-test")
        assert p.name == "tavily"


# ── Factory ────────────────────────────────────────────────────────────


class TestFactory:
    def test_create_brave(self):
        p = create_search_provider("brave", api_key="test-key")
        assert p.name == "brave"

    def test_create_tavily(self):
        p = create_search_provider("tavily", api_key="tvly-test")
        assert p.name == "tavily"

    def test_unknown_provider_raises(self):
        with pytest.raises(SearchProviderError, match="Unknown"):
            create_search_provider("google", api_key="test")

    def test_case_insensitive(self):
        p = create_search_provider("BRAVE", api_key="test")
        assert p.name == "brave"
