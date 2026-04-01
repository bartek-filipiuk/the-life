"""Tests for LLM client — mock OpenRouter responses."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm_client import LLMClient, LLMResponse, LLMUsage


@pytest.fixture
def client():
    return LLMClient(api_key="test-key", model="test/model")


class TestInit:
    def test_requires_api_key(self):
        with pytest.raises(ValueError, match="API key is required"):
            LLMClient(api_key="")

    def test_creates_client(self):
        c = LLMClient(api_key="sk-test", model="openai/gpt-4")
        assert c._model == "openai/gpt-4"


class TestDecisionCall:
    @pytest.mark.asyncio
    async def test_returns_parsed_json(self, client):
        mock_response = _make_response(
            content=json.dumps({"intention": "explore nature", "mood": "curious"}),
            prompt_tokens=100,
            completion_tokens=50,
        )

        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_response):
            result = await client.decision_call(
                messages=[{"role": "user", "content": "decide"}]
            )

        assert isinstance(result, LLMResponse)
        assert result.parsed_json is not None
        assert result.parsed_json["intention"] == "explore nature"
        assert result.usage.prompt_tokens == 100
        assert result.usage.completion_tokens == 50
        assert result.usage.total_tokens == 150

    @pytest.mark.asyncio
    async def test_with_tool_calls(self, client):
        mock_response = _make_response(
            content="",
            tool_calls=[
                _make_tool_call("tc1", "web_search", {"query": "test"}),
            ],
        )

        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_response):
            result = await client.decision_call(
                messages=[{"role": "user", "content": "decide"}],
                tools=[{"type": "function", "function": {"name": "web_search"}}],
            )

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "web_search"
        assert result.tool_calls[0]["arguments"] == {"query": "test"}


class TestCreationCall:
    @pytest.mark.asyncio
    async def test_returns_content(self, client):
        room_data = {"title": "Test Room", "content": "A poem about AI"}
        mock_response = _make_response(content=json.dumps(room_data))

        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_response):
            result = await client.creation_call(
                messages=[{"role": "user", "content": "create"}]
            )

        assert result.parsed_json is not None
        assert result.parsed_json["title"] == "Test Room"


class TestRetry:
    @pytest.mark.asyncio
    async def test_retries_on_rate_limit(self, client):
        from openai import RateLimitError

        mock_create = AsyncMock(
            side_effect=[
                RateLimitError("rate limited", response=MagicMock(status_code=429), body=None),
                _make_response(content='{"ok": true}'),
            ]
        )

        with patch.object(client._client.chat.completions, "create", mock_create):
            result = await client.decision_call(
                messages=[{"role": "user", "content": "test"}]
            )

        assert result.parsed_json == {"ok": True}
        assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_fails_after_max_retries(self, client):
        from openai import RateLimitError

        mock_create = AsyncMock(
            side_effect=RateLimitError("rate limited", response=MagicMock(status_code=429), body=None)
        )

        with patch.object(client._client.chat.completions, "create", mock_create):
            with pytest.raises(RuntimeError, match="failed after"):
                await client.decision_call(
                    messages=[{"role": "user", "content": "test"}]
                )

    @pytest.mark.asyncio
    async def test_retries_on_timeout(self, client):
        from openai import APITimeoutError

        mock_create = AsyncMock(
            side_effect=[
                APITimeoutError(request=MagicMock()),
                _make_response(content='{"ok": true}'),
            ]
        )

        with patch.object(client._client.chat.completions, "create", mock_create):
            result = await client.decision_call(
                messages=[{"role": "user", "content": "test"}]
            )

        assert result.parsed_json == {"ok": True}


class TestCostTracking:
    @pytest.mark.asyncio
    async def test_tracks_usage(self, client):
        mock_response = _make_response(
            content='{"test": true}',
            prompt_tokens=200,
            completion_tokens=100,
            model="openai/gpt-5.4",
        )

        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_response):
            result = await client.decision_call(
                messages=[{"role": "user", "content": "test"}]
            )

        assert result.usage.prompt_tokens == 200
        assert result.usage.completion_tokens == 100
        assert result.usage.total_tokens == 300
        assert result.usage.model == "openai/gpt-5.4"
        assert result.usage.duration_ms >= 0


class TestInvalidResponse:
    @pytest.mark.asyncio
    async def test_non_json_content(self, client):
        mock_response = _make_response(content="This is not JSON")

        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_response):
            result = await client.decision_call(
                messages=[{"role": "user", "content": "test"}]
            )

        assert result.content == "This is not JSON"
        assert result.parsed_json is None

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        mock_response = _make_response(content="")

        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock, return_value=mock_response):
            result = await client.creation_call(
                messages=[{"role": "user", "content": "test"}]
            )

        assert result.content == ""
        assert result.parsed_json is None


# ── Test helpers ───────────────────────────────────────────────────────


def _make_response(
    content: str = "",
    tool_calls: list | None = None,
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
    model: str = "test/model",
) -> MagicMock:
    """Create a mock OpenAI chat completion response."""
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls

    choice = MagicMock()
    choice.message = message

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    response.model = model
    return response


def _make_tool_call(tc_id: str, name: str, arguments: dict) -> MagicMock:
    """Create a mock tool call object."""
    tc = MagicMock()
    tc.id = tc_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc
