"""Shared helpers for API routes."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import HTTPException


def validate_uuid(value: str) -> None:
    """Validate that a string is a valid UUID v4. Raises HTTPException on failure."""
    try:
        UUID(value, version=4)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid room ID format")


def parse_room_data(room: dict[str, Any]) -> dict[str, Any]:
    """Extract room data dict from DB row, handling both JSON and pre-parsed formats."""
    if "data" in room and isinstance(room["data"], str):
        data = json.loads(room["data"])
    elif "title" in room:
        data = room
    else:
        data = room.get("data", room)

    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    data["tags"] = tags
    return data
