"""Tests for app.storage.sqlite_store — CRUD, pagination, stats, security."""

import uuid
from typing import Any

import pytest
import pytest_asyncio

from app.storage.sqlite_store import SQLiteStore, _validate_uuid


def _make_room(
    cycle_number: int = 1,
    room_id: str | None = None,
    created_at: str = "2026-04-01T12:00:00Z",
    **overrides: Any,
) -> dict[str, Any]:
    """Helper to build a room dict for testing."""
    room: dict[str, Any] = {
        "id": room_id or str(uuid.uuid4()),
        "cycle_number": cycle_number,
        "created_at": created_at,
        "title": f"Room {cycle_number}",
        "content": f"Content for room {cycle_number}",
        "model": "openai/gpt-5.4",
        "llm_tokens": 500,
        "llm_cost": 0.05,
        "image_cost": 0.10,
        "music_cost": 0.08,
        "search_cost": 0.01,
        "total_cost": 0.24,
        "duration_ms": 3000,
    }
    room.update(overrides)
    return room


@pytest_asyncio.fixture
async def store(tmp_path) -> SQLiteStore:
    """Create a connected SQLiteStore using a temp database."""
    db_path = str(tmp_path / "test.db")
    s = SQLiteStore(db_path)
    await s.connect()
    yield s
    await s.close()


class TestConnection:
    """Test connect/close lifecycle."""

    @pytest.mark.asyncio
    async def test_db_property_raises_when_not_connected(self, tmp_path) -> None:
        s = SQLiteStore(str(tmp_path / "test.db"))
        with pytest.raises(RuntimeError, match="not connected"):
            _ = s.db

    @pytest.mark.asyncio
    async def test_connect_creates_tables(self, store: SQLiteStore) -> None:
        cursor = await store.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        rows = await cursor.fetchall()
        names = [r["name"] for r in rows]
        assert "rooms" in names
        assert "stats" in names
        assert "config" in names

    @pytest.mark.asyncio
    async def test_close_sets_db_none(self, tmp_path) -> None:
        s = SQLiteStore(str(tmp_path / "test.db"))
        await s.connect()
        await s.close()
        assert s._db is None


class TestInsertRoom:
    """Test room insertion."""

    @pytest.mark.asyncio
    async def test_insert_and_retrieve(self, store: SQLiteStore) -> None:
        room = _make_room(cycle_number=1)
        await store.insert_room(room)
        result = await store.get_room_by_id(room["id"])
        assert result is not None
        assert result["id"] == room["id"]
        assert result["title"] == "Room 1"

    @pytest.mark.asyncio
    async def test_insert_creates_stats_row(self, store: SQLiteStore) -> None:
        room = _make_room(cycle_number=1)
        await store.insert_room(room)
        cursor = await store.db.execute(
            "SELECT * FROM stats WHERE id = ?", (room["id"],)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert float(row["total_cost"]) == 0.24
        assert int(row["llm_tokens"]) == 500

    @pytest.mark.asyncio
    async def test_insert_duplicate_cycle_raises(self, store: SQLiteStore) -> None:
        room1 = _make_room(cycle_number=1)
        room2 = _make_room(cycle_number=1)
        await store.insert_room(room1)
        with pytest.raises(Exception):
            await store.insert_room(room2)

    @pytest.mark.asyncio
    async def test_insert_invalid_uuid_raises(self, store: SQLiteStore) -> None:
        room = _make_room(room_id="not-a-uuid")
        with pytest.raises(ValueError, match="Invalid UUID"):
            await store.insert_room(room)


class TestGetRoomById:
    """Test get_room_by_id."""

    @pytest.mark.asyncio
    async def test_get_existing_room(self, store: SQLiteStore) -> None:
        room = _make_room()
        await store.insert_room(room)
        result = await store.get_room_by_id(room["id"])
        assert result is not None
        assert result["content"] == room["content"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_room(self, store: SQLiteStore) -> None:
        fake_id = str(uuid.uuid4())
        result = await store.get_room_by_id(fake_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_invalid_uuid_raises(self, store: SQLiteStore) -> None:
        with pytest.raises(ValueError, match="Invalid UUID"):
            await store.get_room_by_id("../etc/passwd")


class TestListRoomsPaginated:
    """Test paginated room listing."""

    @pytest.mark.asyncio
    async def test_empty_list(self, store: SQLiteStore) -> None:
        rooms = await store.list_rooms_paginated()
        assert rooms == []

    @pytest.mark.asyncio
    async def test_returns_descending_by_cycle(self, store: SQLiteStore) -> None:
        for i in range(1, 4):
            await store.insert_room(_make_room(cycle_number=i))
        rooms = await store.list_rooms_paginated()
        assert [r["cycle_number"] for r in rooms] == [3, 2, 1]

    @pytest.mark.asyncio
    async def test_pagination_page_size(self, store: SQLiteStore) -> None:
        for i in range(1, 6):
            await store.insert_room(_make_room(cycle_number=i))
        page1 = await store.list_rooms_paginated(page=1, per_page=2)
        page2 = await store.list_rooms_paginated(page=2, per_page=2)
        page3 = await store.list_rooms_paginated(page=3, per_page=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert len(page3) == 1

    @pytest.mark.asyncio
    async def test_per_page_clamped_to_100(self, store: SQLiteStore) -> None:
        room = _make_room(cycle_number=1)
        await store.insert_room(room)
        # Should not error even with per_page > 100
        rooms = await store.list_rooms_paginated(per_page=200)
        assert len(rooms) == 1

    @pytest.mark.asyncio
    async def test_per_page_minimum_is_1(self, store: SQLiteStore) -> None:
        room = _make_room(cycle_number=1)
        await store.insert_room(room)
        rooms = await store.list_rooms_paginated(per_page=0)
        assert len(rooms) == 1

    @pytest.mark.asyncio
    async def test_page_minimum_is_1(self, store: SQLiteStore) -> None:
        room = _make_room(cycle_number=1)
        await store.insert_room(room)
        rooms = await store.list_rooms_paginated(page=0)
        assert len(rooms) == 1


class TestListRoomsByDay:
    """Test day-based room listing."""

    @pytest.mark.asyncio
    async def test_filter_by_day(self, store: SQLiteStore) -> None:
        await store.insert_room(
            _make_room(cycle_number=1, created_at="2026-04-01T10:00:00Z")
        )
        await store.insert_room(
            _make_room(cycle_number=2, created_at="2026-04-01T14:00:00Z")
        )
        await store.insert_room(
            _make_room(cycle_number=3, created_at="2026-04-02T08:00:00Z")
        )
        rooms = await store.list_rooms_by_day("2026-04-01")
        assert len(rooms) == 2
        assert rooms[0]["cycle_number"] == 1  # ascending order

    @pytest.mark.asyncio
    async def test_no_rooms_on_day(self, store: SQLiteStore) -> None:
        rooms = await store.list_rooms_by_day("2026-12-25")
        assert rooms == []


class TestCountRooms:
    """Test room counting."""

    @pytest.mark.asyncio
    async def test_count_empty(self, store: SQLiteStore) -> None:
        assert await store.count_rooms() == 0

    @pytest.mark.asyncio
    async def test_count_after_inserts(self, store: SQLiteStore) -> None:
        for i in range(1, 4):
            await store.insert_room(_make_room(cycle_number=i))
        assert await store.count_rooms() == 3


class TestStatsAggregation:
    """Test stats queries."""

    @pytest.mark.asyncio
    async def test_total_cost_empty(self, store: SQLiteStore) -> None:
        assert await store.get_total_cost() == 0.0

    @pytest.mark.asyncio
    async def test_total_cost_sums(self, store: SQLiteStore) -> None:
        await store.insert_room(_make_room(cycle_number=1, total_cost=0.50))
        await store.insert_room(_make_room(cycle_number=2, total_cost=0.30))
        total = await store.get_total_cost()
        assert abs(total - 0.80) < 0.001

    @pytest.mark.asyncio
    async def test_total_tokens_empty(self, store: SQLiteStore) -> None:
        assert await store.get_total_tokens() == 0

    @pytest.mark.asyncio
    async def test_total_tokens_sums(self, store: SQLiteStore) -> None:
        await store.insert_room(_make_room(cycle_number=1, llm_tokens=100))
        await store.insert_room(_make_room(cycle_number=2, llm_tokens=200))
        assert await store.get_total_tokens() == 300

    @pytest.mark.asyncio
    async def test_cost_per_day(self, store: SQLiteStore) -> None:
        await store.insert_room(
            _make_room(cycle_number=1, created_at="2026-04-01T10:00:00Z", total_cost=0.50)
        )
        await store.insert_room(
            _make_room(cycle_number=2, created_at="2026-04-01T14:00:00Z", total_cost=0.30)
        )
        await store.insert_room(
            _make_room(cycle_number=3, created_at="2026-04-02T08:00:00Z", total_cost=0.20)
        )
        result = await store.get_cost_per_day()
        assert len(result) == 2
        assert result[0]["day"] == "2026-04-01"
        assert abs(result[0]["cost"] - 0.80) < 0.001
        assert result[0]["rooms"] == 2
        assert result[1]["day"] == "2026-04-02"
        assert abs(result[1]["cost"] - 0.20) < 0.001

    @pytest.mark.asyncio
    async def test_daily_cost(self, store: SQLiteStore) -> None:
        await store.insert_room(
            _make_room(cycle_number=1, created_at="2026-04-01T10:00:00Z", total_cost=0.50)
        )
        await store.insert_room(
            _make_room(cycle_number=2, created_at="2026-04-01T14:00:00Z", total_cost=0.30)
        )
        cost = await store.get_daily_cost("2026-04-01")
        assert abs(cost - 0.80) < 0.001

    @pytest.mark.asyncio
    async def test_daily_cost_no_data(self, store: SQLiteStore) -> None:
        cost = await store.get_daily_cost("2026-12-25")
        assert cost == 0.0


class TestConfig:
    """Test config key/value storage."""

    @pytest.mark.asyncio
    async def test_get_missing_key(self, store: SQLiteStore) -> None:
        assert await store.get_config("nonexistent") is None

    @pytest.mark.asyncio
    async def test_set_and_get(self, store: SQLiteStore) -> None:
        await store.set_config("theme", "dark")
        assert await store.get_config("theme") == "dark"

    @pytest.mark.asyncio
    async def test_upsert(self, store: SQLiteStore) -> None:
        await store.set_config("theme", "dark")
        await store.set_config("theme", "light")
        assert await store.get_config("theme") == "light"


class TestValidateUuid:
    """Test the UUID validation helper."""

    def test_valid_uuid4(self) -> None:
        _validate_uuid(str(uuid.uuid4()))  # should not raise

    def test_invalid_string(self) -> None:
        with pytest.raises(ValueError, match="Invalid UUID"):
            _validate_uuid("not-a-uuid")

    def test_path_traversal_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid UUID"):
            _validate_uuid("../../etc/passwd")

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid UUID"):
            _validate_uuid("")

    def test_sql_injection_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid UUID"):
            _validate_uuid("'; DROP TABLE rooms; --")


class TestParameterizedQueries:
    """Verify that SQL injection via room data is not possible."""

    @pytest.mark.asyncio
    async def test_malicious_room_content_is_safe(self, store: SQLiteStore) -> None:
        """Room content with SQL-like strings should be stored safely as data."""
        room = _make_room(
            cycle_number=1,
            title="'; DROP TABLE rooms; --",
            content="Robert'); DROP TABLE stats;--",
        )
        await store.insert_room(room)
        result = await store.get_room_by_id(room["id"])
        assert result is not None
        assert result["title"] == "'; DROP TABLE rooms; --"
        # Verify tables still exist
        assert await store.count_rooms() == 1

    @pytest.mark.asyncio
    async def test_malicious_day_filter_is_safe(self, store: SQLiteStore) -> None:
        """SQL injection via day parameter should be harmless."""
        rooms = await store.list_rooms_by_day("2026-04-01' OR '1'='1")
        assert rooms == []

    @pytest.mark.asyncio
    async def test_malicious_config_key_is_safe(self, store: SQLiteStore) -> None:
        """SQL injection via config key should be harmless."""
        await store.set_config("key'; DROP TABLE config; --", "value")
        result = await store.get_config("key'; DROP TABLE config; --")
        assert result == "value"
