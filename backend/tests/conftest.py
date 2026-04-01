"""Shared test fixtures."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from app.storage.sqlite_store import SQLiteStore


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def test_settings(tmp_dir):
    return Settings(
        openrouter_api_key="test-key",
        replicate_api_token="test-token",
        brave_api_key="test-brave",
    )


@pytest.fixture
def sample_room_data():
    """Return a sample room data dict."""
    return {
        "id": "aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee",
        "cycle_number": 1,
        "created_at": "2026-04-01T12:00:00Z",
        "title": "Test Room",
        "content": "A beautiful poem about testing",
        "content_type": "poem",
        "mood": "curious",
        "tags": ["testing", "poetry"],
        "image_url": None,
        "music_url": None,
        "intention": "explore testing",
        "reasoning": "tests are important",
        "search_queries": [],
        "search_results": [],
        "connections": [],
        "model": "test/model",
        "llm_tokens": 100,
        "total_cost": 0.05,
        "duration_ms": 1000,
    }


@pytest.fixture
async def sqlite_store(tmp_dir):
    """Create an initialized SQLite store for testing."""
    db_path = str(tmp_dir / "test.db")
    store = SQLiteStore(db_path)
    await store.init()
    yield store
    await store.close()
