"""Tests for comment moderation."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.moderation import Moderator, ModerationConfig, hash_ip
from app.storage.sqlite_store import SQLiteStore


@pytest.fixture
async def moderator():
    """Create moderator with temporary SQLite."""
    with tempfile.TemporaryDirectory() as d:
        store = SQLiteStore(str(Path(d) / "test.db"))
        await store.connect()
        mod = Moderator(store)
        await mod.load_config()
        yield mod
        await store.close()


@pytest.mark.asyncio
async def test_accepts_valid_comment(moderator):
    result = await moderator.check("Great content!", "Alice", hash_ip("1.2.3.4"))
    assert result.approved is True


@pytest.mark.asyncio
async def test_rejects_empty_content(moderator):
    result = await moderator.check("", "Alice", hash_ip("1.2.3.4"))
    assert result.approved is False
    assert "empty" in result.reason.lower()


@pytest.mark.asyncio
async def test_rejects_empty_name_when_required(moderator):
    result = await moderator.check("Hello!", "", hash_ip("1.2.3.4"))
    assert result.approved is False
    assert "Name" in result.reason


@pytest.mark.asyncio
async def test_rejects_too_long_content(moderator):
    result = await moderator.check("x" * 1001, "Alice", hash_ip("1.2.3.4"))
    assert result.approved is False
    assert "1000" in result.reason


@pytest.mark.asyncio
async def test_banned_words_filter(moderator):
    config = moderator.config
    config.banned_words = ["spam"]
    await moderator.save_config(config)
    await moderator.load_config()

    result = await moderator.check("This is spam content", "Alice", hash_ip("1.2.3.4"))
    assert result.approved is False
    assert "prohibited" in result.reason.lower()


@pytest.mark.asyncio
async def test_rate_limiting(moderator):
    config = moderator.config
    config.rate_limit_per_hour = 2
    await moderator.save_config(config)
    await moderator.load_config()

    ip = hash_ip("5.6.7.8")
    # Insert fake comments to simulate rate limit
    from datetime import datetime, timezone
    import uuid
    for i in range(2):
        await moderator._sqlite.insert_comment({
            "id": str(uuid.uuid4()),
            "room_id": str(uuid.uuid4()),
            "author_name": "Test",
            "content": f"Comment {i}",
            "status": "approved",
            "ip_hash": ip,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    result = await moderator.check("Another comment", "Alice", ip)
    assert result.approved is False
    assert "Rate limit" in result.reason


def test_hash_ip():
    h = hash_ip("192.168.1.1")
    assert len(h) == 16
    assert h == hash_ip("192.168.1.1")  # deterministic
    assert h != hash_ip("192.168.1.2")  # different IPs
