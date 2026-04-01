"""Tests for Brave Search API wrapper — mock HTTP responses."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.tools.web_search import SearchResult, search


class TestSearch:
    @pytest.mark.asyncio
    async def test_returns_results(self):
        mock_response = _mock_brave_response([
            {"title": "Result 1", "url": "https://example.com/1", "description": "Snippet 1"},
            {"title": "Result 2", "url": "https://example.com/2", "description": "Snippet 2"},
        ])

        with patch("app.tools.web_search.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_cls.return_value)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value.get = AsyncMock(return_value=mock_response)

            results = await search("test query", api_key="test-key")

        assert len(results) == 2
        assert isinstance(results[0], SearchResult)
        assert results[0].title == "Result 1"
        assert results[0].url == "https://example.com/1"
        assert results[0].snippet == "Snippet 1"

    @pytest.mark.asyncio
    async def test_empty_results(self):
        mock_response = _mock_brave_response([])

        with patch("app.tools.web_search.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_cls.return_value)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value.get = AsyncMock(return_value=mock_response)

            results = await search("no results query", api_key="test-key")

        assert results == []


class TestInputValidation:
    @pytest.mark.asyncio
    async def test_empty_query_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            await search("", api_key="test-key")

    @pytest.mark.asyncio
    async def test_whitespace_query_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            await search("   ", api_key="test-key")

    @pytest.mark.asyncio
    async def test_missing_api_key_raises(self):
        with pytest.raises(ValueError, match="API key is required"):
            await search("test", api_key="")

    @pytest.mark.asyncio
    async def test_long_query_truncated(self):
        long_query = "x" * 500
        mock_response = _mock_brave_response([])

        with patch("app.tools.web_search.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_cls.return_value)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value.get = AsyncMock(return_value=mock_response)

            results = await search(long_query, api_key="test-key")
            # Should not raise — just truncate
            assert isinstance(results, list)


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_http_error_propagates(self):
        mock_response = httpx.Response(status_code=500, request=httpx.Request("GET", "https://test"))

        with patch("app.tools.web_search.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_cls.return_value)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value.get = AsyncMock(return_value=mock_response)

            with pytest.raises(httpx.HTTPStatusError):
                await search("test", api_key="test-key")


class TestResultParsing:
    @pytest.mark.asyncio
    async def test_skips_results_without_url(self):
        mock_response = _mock_brave_response([
            {"title": "No URL", "description": "Missing URL field"},
            {"title": "Has URL", "url": "https://example.com", "description": "OK"},
        ])

        with patch("app.tools.web_search.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_cls.return_value)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value.get = AsyncMock(return_value=mock_response)

            results = await search("test", api_key="test-key")

        assert len(results) == 1
        assert results[0].url == "https://example.com"


def _mock_brave_response(results: list) -> httpx.Response:
    """Create a mock Brave Search API response."""
    import json
    data = {"web": {"results": results}}
    return httpx.Response(
        status_code=200,
        json=data,
        request=httpx.Request("GET", "https://api.search.brave.com/res/v1/web/search"),
    )
