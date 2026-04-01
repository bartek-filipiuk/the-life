"""REST API endpoints.

Security: rate limiting on POST /trigger, UUID validation, pagination limits.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.api.schemas import (
    GraphEdge,
    GraphNode,
    GraphResponse,
    HealthResponse,
    PaginatedRooms,
    RoomResponse,
    RoomSummary,
    StatsResponse,
    TimelineDayResponse,
    TimelineResponse,
    TriggerResponse,
)

router = APIRouter()

# Rate limiting state for POST /trigger
_last_trigger_time: float = 0.0
_TRIGGER_COOLDOWN = 60.0  # 1 minute


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    sqlite = request.app.state.sqlite
    count = await sqlite.count_rooms()
    return HealthResponse(status="ok", cycle_count=count)


@router.get("/rooms", response_model=PaginatedRooms)
async def list_rooms(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
) -> PaginatedRooms:
    sqlite = request.app.state.sqlite
    total = await sqlite.count_rooms()
    rooms_raw = await sqlite.list_rooms_paginated(page=page, per_page=per_page)
    rooms = [_to_summary(r) for r in rooms_raw]
    return PaginatedRooms(rooms=rooms, total=total, page=page, per_page=per_page)


@router.get("/rooms/{room_id}", response_model=RoomResponse)
async def get_room(request: Request, room_id: str) -> RoomResponse:
    _validate_uuid(room_id)
    sqlite = request.app.state.sqlite
    room = await sqlite.get_room_by_id(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    # get_room_by_id returns parsed dict
    data = room if "title" in room else json.loads(room.get("data", "{}"))
    return RoomResponse(**data)


@router.get("/graph", response_model=GraphResponse)
async def get_graph(request: Request) -> GraphResponse:
    sqlite = request.app.state.sqlite
    all_rooms = await sqlite.list_rooms_paginated(page=1, per_page=10000)

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    connection_count: dict[str, int] = {}

    # First pass: collect connections
    for room in all_rooms:
        data = room if "title" in room else json.loads(room.get("data", "{}"))
        connections = data.get("connections", [])
        room_id = data.get("id", room.get("id", ""))
        connection_count[room_id] = len(connections)
        for target in connections:
            edges.append(GraphEdge(source=room_id, target=target))

    # Second pass: build nodes
    for room in all_rooms:
        data = room if "title" in room else json.loads(room.get("data", "{}"))
        room_id = room.get("id", data.get("id", ""))
        tags = data.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        nodes.append(GraphNode(
            id=room_id,
            label=data.get("title", "Untitled"),
            content_type=data.get("content_type", ""),
            mood=data.get("mood", ""),
            tags=tags,
            cycle_number=data.get("cycle_number", 0),
            size=connection_count.get(room_id, 0) + 1,
        ))

    return GraphResponse(nodes=nodes, edges=edges)


@router.get("/stats", response_model=StatsResponse)
async def get_stats(request: Request) -> StatsResponse:
    sqlite = request.app.state.sqlite
    settings = request.app.state.settings
    total_rooms = await sqlite.count_rooms()
    total_cost = await sqlite.get_total_cost()
    total_tokens = await sqlite.get_total_tokens()
    cost_per_day = await sqlite.get_cost_per_day()
    return StatsResponse(
        total_rooms=total_rooms,
        total_cost=total_cost,
        total_tokens=total_tokens,
        cost_per_day=cost_per_day,
        model=settings.model,
    )


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(request: Request) -> TimelineResponse:
    sqlite = request.app.state.sqlite
    cost_per_day = await sqlite.get_cost_per_day()
    days: list[TimelineDayResponse] = []

    for day_entry in cost_per_day:
        date = day_entry.get("day", "")
        rooms_raw = await sqlite.list_rooms_by_day(date)
        rooms = [_to_summary(r) for r in rooms_raw]
        days.append(TimelineDayResponse(date=date, rooms=rooms))

    return TimelineResponse(days=days)


@router.get("/current-cycle")
async def current_cycle_sse(request: Request) -> StreamingResponse:
    """SSE endpoint streaming the current cycle's logs."""
    async def event_stream():
        engine = getattr(request.app.state, "cycle_engine", None)
        last_log_count = 0
        for _ in range(300):  # max 5 min
            if engine and hasattr(engine, "_current_result"):
                result = engine._current_result
                if result and hasattr(result, "logs"):
                    new_logs = result.logs[last_log_count:]
                    for log in new_logs:
                        yield f"data: {json.dumps({'log': log})}\n\n"
                    last_log_count = len(result.logs)
            yield f"data: {json.dumps({'heartbeat': True})}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_cycle(request: Request) -> TriggerResponse:
    """Manually trigger an AI cycle. Rate limited to 1/min."""
    global _last_trigger_time
    now = time.monotonic()
    if now - _last_trigger_time < _TRIGGER_COOLDOWN:
        remaining = int(_TRIGGER_COOLDOWN - (now - _last_trigger_time))
        raise HTTPException(
            status_code=429,
            detail=f"Rate limited. Try again in {remaining}s",
        )
    _last_trigger_time = now

    engine = getattr(request.app.state, "cycle_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="Cycle engine not initialized")

    result = await engine.run_cycle()
    if result.success:
        return TriggerResponse(status="ok", message="Cycle completed", room_id=result.room_id)
    return TriggerResponse(status="error", message=result.error or "Unknown error")


# ── Helpers ────────────────────────────────────────────────────────────


def _validate_uuid(value: str) -> None:
    """Validate that a string is a valid UUID."""
    try:
        UUID(value, version=4)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid room ID format")


def _to_summary(room: dict[str, Any]) -> RoomSummary:
    """Convert a room dict to RoomSummary.

    Handles both formats: pre-parsed dict (from list_rooms_paginated)
    and raw row with 'data' JSON column.
    """
    if "data" in room and isinstance(room["data"], str):
        data = json.loads(room["data"])
    elif "title" in room:
        data = room  # already parsed
    else:
        data = room.get("data", room)

    tags = data.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return RoomSummary(
        id=data.get("id", room.get("id", "")),
        cycle_number=data.get("cycle_number", 0),
        created_at=data.get("created_at", ""),
        title=data.get("title", "Untitled"),
        content_type=data.get("content_type", ""),
        mood=data.get("mood", ""),
        tags=tags,
        total_cost=data.get("total_cost", 0.0),
        has_image=bool(data.get("image_url")),
        has_music=bool(data.get("music_url")),
    )
