"""Tests for the dynamic tool registry."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.storage.sqlite_store import SQLiteStore
from app.tools.registry import ToolRegistry, DEFAULT_TOOLS


@pytest.fixture
async def registry():
    """Create registry with temporary SQLite."""
    with tempfile.TemporaryDirectory() as d:
        store = SQLiteStore(str(Path(d) / "test.db"))
        await store.connect()
        reg = ToolRegistry(store)
        await reg.load()
        yield reg
        await store.close()


@pytest.mark.asyncio
async def test_loads_default_tools(registry):
    tools = registry.list_tools()
    assert len(tools) == len(DEFAULT_TOOLS)
    assert registry.get_tool("web_search") is not None
    assert registry.get_tool("generate_image") is not None


@pytest.mark.asyncio
async def test_toggle_tool(registry):
    tool = registry.get_tool("generate_image")
    assert tool.enabled is True

    await registry.update_tool("generate_image", {"enabled": False})
    tool = registry.get_tool("generate_image")
    assert tool.enabled is False


@pytest.mark.asyncio
async def test_daily_limit_enforcement(registry):
    assert registry.is_available("web_search") is True

    # Record up to limit
    tool = registry.get_tool("web_search")
    for _ in range(tool.daily_limit):
        await registry.record_usage("web_search")

    assert registry.is_available("web_search") is False


@pytest.mark.asyncio
async def test_add_custom_tool(registry):
    tool = await registry.add_tool({
        "id": "youtube_articles",
        "name": "YouTube Articles",
        "category": "custom",
        "api_type": "custom_http",
        "provider": "custom",
        "model": "",
        "daily_limit": 10,
        "config": {"endpoint_url": "https://example.com/api"},
    })
    assert tool.id == "youtube_articles"
    assert registry.get_tool("youtube_articles") is not None
    assert len(registry.list_tools()) == len(DEFAULT_TOOLS) + 1


@pytest.mark.asyncio
async def test_remove_tool(registry):
    await registry.add_tool({
        "id": "temp_tool", "name": "Temp", "category": "custom",
        "api_type": "custom_http", "provider": "", "model": "",
    })
    assert await registry.remove_tool("temp_tool") is True
    assert registry.get_tool("temp_tool") is None


@pytest.mark.asyncio
async def test_build_tool_definitions(registry):
    defs = registry.build_tool_definitions()
    names = [d["function"]["name"] for d in defs]
    assert "web_search" in names
    assert "generate_image" in names
    # generate_video is disabled by default
    assert "generate_video" not in names


@pytest.mark.asyncio
async def test_build_tool_names(registry):
    names = registry.build_tool_names_for_prompt()
    assert "web_search" in names
    assert "generate_image" in names


@pytest.mark.asyncio
async def test_disabled_tool_not_in_enabled_list(registry):
    await registry.update_tool("generate_music", {"enabled": False})
    enabled = registry.get_enabled_tools()
    ids = [t.id for t in enabled]
    assert "generate_music" not in ids
