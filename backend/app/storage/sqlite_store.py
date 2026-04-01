"""Async SQLite storage for rooms, stats, and config.

Security: all queries use parameterized placeholders — never string formatting.
"""

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import aiosqlite

_CREATE_ROOMS = """
CREATE TABLE IF NOT EXISTS rooms (
    id            TEXT PRIMARY KEY,
    cycle_number  INTEGER NOT NULL UNIQUE,
    created_at    TEXT NOT NULL,
    data          TEXT NOT NULL  -- full Room JSON
);
"""

_CREATE_ROOMS_IDX_CYCLE = """
CREATE INDEX IF NOT EXISTS idx_rooms_cycle ON rooms (cycle_number);
"""

_CREATE_ROOMS_IDX_DATE = """
CREATE INDEX IF NOT EXISTS idx_rooms_created ON rooms (created_at);
"""

_CREATE_STATS = """
CREATE TABLE IF NOT EXISTS stats (
    id           TEXT PRIMARY KEY,
    cycle_number INTEGER NOT NULL,
    created_at   TEXT NOT NULL,
    model        TEXT NOT NULL,
    llm_tokens   INTEGER NOT NULL DEFAULT 0,
    llm_cost     REAL NOT NULL DEFAULT 0.0,
    image_cost   REAL NOT NULL DEFAULT 0.0,
    music_cost   REAL NOT NULL DEFAULT 0.0,
    search_cost  REAL NOT NULL DEFAULT 0.0,
    total_cost   REAL NOT NULL DEFAULT 0.0,
    duration_ms  INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_STATS_IDX = """
CREATE INDEX IF NOT EXISTS idx_stats_created ON stats (created_at);
"""

_CREATE_CONFIG = """
CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class SQLiteStore:
    """Async SQLite wrapper for The Life data."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open the database and create tables if needed."""
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute(_CREATE_ROOMS)
        await self._db.execute(_CREATE_ROOMS_IDX_CYCLE)
        await self._db.execute(_CREATE_ROOMS_IDX_DATE)
        await self._db.execute(_CREATE_STATS)
        await self._db.execute(_CREATE_STATS_IDX)
        await self._db.execute(_CREATE_CONFIG)
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("SQLiteStore is not connected. Call connect() first.")
        return self._db

    # ── Rooms ────────────────────────────────────────────────────────────

    async def insert_room(self, room: dict[str, Any]) -> None:
        """Insert a room record. `room` must contain id, cycle_number, created_at."""
        room_id = str(room["id"])
        _validate_uuid(room_id)
        await self.db.execute(
            "INSERT INTO rooms (id, cycle_number, created_at, data) VALUES (?, ?, ?, ?)",
            (room_id, room["cycle_number"], room["created_at"], json.dumps(room)),
        )
        # Insert corresponding stats row
        await self.db.execute(
            """INSERT INTO stats
               (id, cycle_number, created_at, model,
                llm_tokens, llm_cost, image_cost, music_cost, search_cost, total_cost, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                room_id,
                room["cycle_number"],
                room["created_at"],
                room.get("model", ""),
                room.get("llm_tokens", 0),
                room.get("llm_cost", 0.0),
                room.get("image_cost", 0.0),
                room.get("music_cost", 0.0),
                room.get("search_cost", 0.0),
                room.get("total_cost", 0.0),
                room.get("duration_ms", 0),
            ),
        )
        await self.db.commit()

    async def get_room_by_id(self, room_id: str) -> dict[str, Any] | None:
        """Get a single room by UUID."""
        _validate_uuid(room_id)
        cursor = await self.db.execute(
            "SELECT data FROM rooms WHERE id = ?", (room_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return json.loads(row["data"])

    async def list_rooms_paginated(
        self, page: int = 1, per_page: int = 20
    ) -> list[dict[str, Any]]:
        """List rooms ordered by cycle_number descending, with pagination."""
        if per_page < 1:
            per_page = 1
        if per_page > 100:
            per_page = 100
        if page < 1:
            page = 1
        offset = (page - 1) * per_page
        cursor = await self.db.execute(
            "SELECT data FROM rooms ORDER BY cycle_number DESC LIMIT ? OFFSET ?",
            (per_page, offset),
        )
        rows = await cursor.fetchall()
        return [json.loads(r["data"]) for r in rows]

    async def list_rooms_by_day(self, day: str) -> list[dict[str, Any]]:
        """List rooms created on a given day (YYYY-MM-DD)."""
        cursor = await self.db.execute(
            "SELECT data FROM rooms WHERE created_at LIKE ? ORDER BY cycle_number ASC",
            (f"{day}%",),
        )
        rows = await cursor.fetchall()
        return [json.loads(r["data"]) for r in rows]

    async def count_rooms(self) -> int:
        """Return the total number of rooms."""
        cursor = await self.db.execute("SELECT COUNT(*) as cnt FROM rooms")
        row = await cursor.fetchone()
        return row["cnt"] if row else 0

    # ── Stats Aggregation ────────────────────────────────────────────────

    async def get_total_cost(self) -> float:
        """Sum of total_cost across all cycles."""
        cursor = await self.db.execute(
            "SELECT COALESCE(SUM(total_cost), 0.0) as total FROM stats"
        )
        row = await cursor.fetchone()
        return float(row["total"]) if row else 0.0

    async def get_total_tokens(self) -> int:
        """Sum of llm_tokens across all cycles."""
        cursor = await self.db.execute(
            "SELECT COALESCE(SUM(llm_tokens), 0) as total FROM stats"
        )
        row = await cursor.fetchone()
        return int(row["total"]) if row else 0

    async def get_cost_per_day(self) -> list[dict[str, Any]]:
        """Aggregate total_cost grouped by day (YYYY-MM-DD)."""
        cursor = await self.db.execute(
            """SELECT DATE(created_at) as day,
                      SUM(total_cost) as cost,
                      SUM(llm_tokens) as tokens,
                      COUNT(*) as rooms
               FROM stats
               GROUP BY DATE(created_at)
               ORDER BY day ASC"""
        )
        rows = await cursor.fetchall()
        return [
            {
                "day": r["day"],
                "cost": float(r["cost"]),
                "tokens": int(r["tokens"]),
                "rooms": int(r["rooms"]),
            }
            for r in rows
        ]

    async def get_daily_cost(self, day: str | None = None) -> float:
        """Get total cost for a specific day (defaults to today UTC)."""
        if day is None:
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cursor = await self.db.execute(
            "SELECT COALESCE(SUM(total_cost), 0.0) as total FROM stats WHERE DATE(created_at) = ?",
            (day,),
        )
        row = await cursor.fetchone()
        return float(row["total"]) if row else 0.0

    # ── Config ───────────────────────────────────────────────────────────

    async def get_config(self, key: str) -> str | None:
        """Get a config value by key."""
        cursor = await self.db.execute(
            "SELECT value FROM config WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row["value"] if row else None

    async def set_config(self, key: str, value: str) -> None:
        """Set a config key/value (upsert)."""
        await self.db.execute(
            "INSERT INTO config (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self.db.commit()


def _validate_uuid(value: str) -> None:
    """Raise ValueError if value is not a valid UUID."""
    try:
        UUID(value, version=4)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid UUID: {value!r}") from exc
