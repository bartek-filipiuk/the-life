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
    data          TEXT NOT NULL,  -- full Room JSON
    status        TEXT NOT NULL DEFAULT 'published'  -- draft, published, featured
);
"""

_CREATE_ROOMS_IDX_CYCLE = """
CREATE INDEX IF NOT EXISTS idx_rooms_cycle ON rooms (cycle_number);
"""

_CREATE_ROOMS_IDX_DATE = """
CREATE INDEX IF NOT EXISTS idx_rooms_created ON rooms (created_at);
"""

_CREATE_ROOMS_IDX_STATUS = """
CREATE INDEX IF NOT EXISTS idx_rooms_status ON rooms (status);
"""

_ADD_STATUS_COLUMN = """
ALTER TABLE rooms ADD COLUMN status TEXT NOT NULL DEFAULT 'published';
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

_CREATE_COMMENTS = """
CREATE TABLE IF NOT EXISTS comments (
    id                TEXT PRIMARY KEY,
    room_id           TEXT NOT NULL,
    author_name       TEXT NOT NULL,
    content           TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    ip_hash           TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    moderation_reason TEXT NOT NULL DEFAULT ''
);
"""

_CREATE_COMMENTS_IDX_ROOM = """
CREATE INDEX IF NOT EXISTS idx_comments_room ON comments (room_id, status);
"""

_CREATE_COMMENTS_IDX_DATE = """
CREATE INDEX IF NOT EXISTS idx_comments_created ON comments (created_at);
"""

_CREATE_CYCLE_LOGS = """
CREATE TABLE IF NOT EXISTS cycle_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_number INTEGER NOT NULL,
    timestamp    TEXT NOT NULL,
    level        TEXT NOT NULL,
    message      TEXT NOT NULL,
    step         TEXT NOT NULL DEFAULT ''
);
"""

_CREATE_CYCLE_LOGS_IDX = """
CREATE INDEX IF NOT EXISTS idx_cycle_logs_cycle ON cycle_logs (cycle_number);
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
        # Migrate: add status column if missing (existing DBs) — must run before status index
        await self._maybe_add_status_column()
        await self._db.execute(_CREATE_ROOMS_IDX_STATUS)
        await self._db.execute(_CREATE_STATS)
        await self._db.execute(_CREATE_STATS_IDX)
        await self._db.execute(_CREATE_CONFIG)
        await self._db.execute(_CREATE_COMMENTS)
        await self._db.execute(_CREATE_COMMENTS_IDX_ROOM)
        await self._db.execute(_CREATE_COMMENTS_IDX_DATE)
        await self._db.execute(_CREATE_CYCLE_LOGS)
        await self._db.execute(_CREATE_CYCLE_LOGS_IDX)
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

    async def _maybe_add_status_column(self) -> None:
        """Add status column to rooms table if it doesn't exist (migration)."""
        cursor = await self.db.execute("PRAGMA table_info(rooms)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "status" not in columns:
            await self.db.execute(_ADD_STATUS_COLUMN)
            await self.db.commit()

    # ── Rooms ────────────────────────────────────────────────────────────

    async def insert_room(self, room: dict[str, Any]) -> None:
        """Insert a room record. `room` must contain id, cycle_number, created_at."""
        room_id = str(room["id"])
        _validate_uuid(room_id)
        status = room.get("status", "published")
        await self.db.execute(
            "INSERT INTO rooms (id, cycle_number, created_at, data, status) VALUES (?, ?, ?, ?, ?)",
            (room_id, room["cycle_number"], room["created_at"], json.dumps(room), status),
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
        """Get a single room by UUID, including status."""
        _validate_uuid(room_id)
        cursor = await self.db.execute(
            "SELECT data, status FROM rooms WHERE id = ?", (room_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        data = json.loads(row["data"])
        data["status"] = row["status"]
        return data

    async def list_rooms_paginated(
        self, page: int = 1, per_page: int = 20, *, status_filter: str | None = "published"
    ) -> list[dict[str, Any]]:
        """List rooms ordered by cycle_number descending, with pagination.

        Pass status_filter=None to return all rooms (admin use).
        """
        if per_page < 1:
            per_page = 1
        if per_page > 100:
            per_page = 100
        if page < 1:
            page = 1
        offset = (page - 1) * per_page
        if status_filter:
            cursor = await self.db.execute(
                "SELECT data, status FROM rooms WHERE status = ? ORDER BY cycle_number DESC LIMIT ? OFFSET ?",
                (status_filter, per_page, offset),
            )
        else:
            cursor = await self.db.execute(
                "SELECT data, status FROM rooms ORDER BY cycle_number DESC LIMIT ? OFFSET ?",
                (per_page, offset),
            )
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            room = json.loads(r["data"])
            room["status"] = r["status"]
            result.append(room)
        return result

    async def list_rooms_by_day(self, day: str, *, status_filter: str | None = "published") -> list[dict[str, Any]]:
        """List rooms created on a given day (YYYY-MM-DD)."""
        if status_filter:
            cursor = await self.db.execute(
                "SELECT data, status FROM rooms WHERE created_at LIKE ? AND status = ? ORDER BY cycle_number ASC",
                (f"{day}%", status_filter),
            )
        else:
            cursor = await self.db.execute(
                "SELECT data, status FROM rooms WHERE created_at LIKE ? ORDER BY cycle_number ASC",
                (f"{day}%",),
            )
        rows = await cursor.fetchall()
        result = []
        for r in rows:
            room = json.loads(r["data"])
            room["status"] = r["status"]
            result.append(room)
        return result

    async def count_rooms(self, *, status_filter: str | None = "published") -> int:
        """Return the total number of rooms, optionally filtered by status."""
        if status_filter:
            cursor = await self.db.execute(
                "SELECT COUNT(*) as cnt FROM rooms WHERE status = ?", (status_filter,)
            )
        else:
            cursor = await self.db.execute("SELECT COUNT(*) as cnt FROM rooms")
        row = await cursor.fetchone()
        return row["cnt"] if row else 0

    async def count_rooms_by_status(self) -> dict[str, int]:
        """Count rooms grouped by status in a single query."""
        cursor = await self.db.execute(
            "SELECT status, COUNT(*) as cnt FROM rooms GROUP BY status"
        )
        rows = await cursor.fetchall()
        return {row["status"]: row["cnt"] for row in rows}

    # ── Admin CRUD ──────────────────────────────────────────────────────

    async def update_room_status(self, room_id: str, status: str) -> bool:
        """Update the publication status of a room. Returns True if found."""
        _validate_uuid(room_id)
        if status not in ("draft", "published", "featured"):
            raise ValueError(f"Invalid status: {status!r}")
        cursor = await self.db.execute(
            "UPDATE rooms SET status = ? WHERE id = ?", (status, room_id)
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def update_room(self, room_id: str, updates: dict[str, Any]) -> bool:
        """Update specific fields in a room's data JSON. Returns True if found."""
        _validate_uuid(room_id)
        cursor = await self.db.execute(
            "SELECT data, status FROM rooms WHERE id = ?", (room_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return False

        data = json.loads(row["data"])
        new_status = row["status"]

        for key, value in updates.items():
            if key == "status":
                new_status = value
            elif value is not None:
                data[key] = value

        await self.db.execute(
            "UPDATE rooms SET data = ?, status = ? WHERE id = ?",
            (json.dumps(data), new_status, room_id),
        )
        await self.db.commit()
        return True

    async def delete_room(self, room_id: str) -> bool:
        """Delete a room and its stats. Returns True if found."""
        _validate_uuid(room_id)
        cursor = await self.db.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        await self.db.execute("DELETE FROM stats WHERE id = ?", (room_id,))
        await self.db.commit()
        return cursor.rowcount > 0

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


    # ── Comments ─────────────────────────────────────────────────────────

    async def insert_comment(self, comment: dict[str, Any]) -> None:
        """Insert a new comment."""
        await self.db.execute(
            """INSERT INTO comments (id, room_id, author_name, content, status, ip_hash, created_at, moderation_reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                comment["id"],
                comment["room_id"],
                comment["author_name"],
                comment["content"],
                comment.get("status", "pending"),
                comment.get("ip_hash", ""),
                comment["created_at"],
                comment.get("moderation_reason", ""),
            ),
        )
        await self.db.commit()

    async def list_comments(
        self, room_id: str, status: str | None = "approved"
    ) -> list[dict[str, Any]]:
        """List comments for a room, optionally filtered by status."""
        if status:
            cursor = await self.db.execute(
                "SELECT * FROM comments WHERE room_id = ? AND status = ? ORDER BY created_at ASC",
                (room_id, status),
            )
        else:
            cursor = await self.db.execute(
                "SELECT * FROM comments WHERE room_id = ? ORDER BY created_at ASC",
                (room_id,),
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def list_all_comments(
        self, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """List all comments, optionally filtered by status."""
        if status:
            cursor = await self.db.execute(
                "SELECT * FROM comments WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            )
        else:
            cursor = await self.db.execute(
                "SELECT * FROM comments ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def update_comment_status(self, comment_id: str, status: str) -> bool:
        """Update a comment's status. Returns True if found."""
        cursor = await self.db.execute(
            "UPDATE comments SET status = ? WHERE id = ?", (status, comment_id)
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def count_recent_comments(self, ip_hash: str) -> int:
        """Count comments from an IP hash in the last hour."""
        cursor = await self.db.execute(
            "SELECT COUNT(*) as cnt FROM comments WHERE ip_hash = ? AND created_at > datetime('now', '-1 hour')",
            (ip_hash,),
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0

    async def get_recent_approved_comments(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent approved comments for AI context."""
        cursor = await self.db.execute(
            "SELECT * FROM comments WHERE status = 'approved' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ── Cycle Logs ──────────────────────────────────────────────────────

    async def insert_log(self, cycle_number: int, timestamp: str, level: str, message: str, step: str = "") -> None:
        """Insert a cycle log entry."""
        await self.db.execute(
            "INSERT INTO cycle_logs (cycle_number, timestamp, level, message, step) VALUES (?, ?, ?, ?, ?)",
            (cycle_number, timestamp, level, message, step),
        )
        await self.db.commit()

    async def list_logs(
        self, limit: int = 100, offset: int = 0, level: str | None = None
    ) -> list[dict[str, Any]]:
        """List cycle logs, newest first."""
        if level:
            cursor = await self.db.execute(
                "SELECT * FROM cycle_logs WHERE level = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (level, limit, offset),
            )
        else:
            cursor = await self.db.execute(
                "SELECT * FROM cycle_logs ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def count_comments(self, status: str | None = None) -> int:
        """Count comments, optionally by status."""
        if status:
            cursor = await self.db.execute(
                "SELECT COUNT(*) as cnt FROM comments WHERE status = ?", (status,)
            )
        else:
            cursor = await self.db.execute("SELECT COUNT(*) as cnt FROM comments")
        row = await cursor.fetchone()
        return row["cnt"] if row else 0


def _validate_uuid(value: str) -> None:
    """Raise ValueError if value is not a valid UUID."""
    try:
        UUID(value, version=4)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid UUID: {value!r}") from exc
