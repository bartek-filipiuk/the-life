"""Admin API endpoints — protected by Bearer token.

Provides CRUD for rooms, runtime config management, scheduler control.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.api.admin_schemas import (
    AdminRoomListResponse,
    AdminRoomResponse,
    AdminTriggerResponse,
    RoomStatusUpdate,
    RoomUpdate,
    RuntimeConfigResponse,
    RuntimeConfigUpdate,
    SchedulerActionResponse,
)
from app.api.auth import require_admin
from app.api.helpers import parse_room_data, validate_uuid

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


# ── Rooms CRUD ──────────────────────────────────────────────────────────


@router.get("/rooms", response_model=AdminRoomListResponse)
async def admin_list_rooms(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Filter by status: draft, published, featured"),
) -> AdminRoomListResponse:
    """List all rooms (all statuses) with optional status filter."""
    sqlite = request.app.state.sqlite
    total = await sqlite.count_rooms(status_filter=status)
    rooms_raw = await sqlite.list_rooms_paginated(
        page=page, per_page=per_page, status_filter=status
    )
    rooms = [_to_admin_room(r) for r in rooms_raw]
    return AdminRoomListResponse(rooms=rooms, total=total, page=page, per_page=per_page)


@router.put("/rooms/{room_id}", response_model=AdminRoomResponse)
async def admin_update_room(
    request: Request, room_id: str, body: RoomUpdate
) -> AdminRoomResponse:
    """Update a room's data fields and/or status."""
    validate_uuid(room_id)
    sqlite = request.app.state.sqlite
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    found = await sqlite.update_room(room_id, updates)
    if not found:
        raise HTTPException(status_code=404, detail="Room not found")

    room = await sqlite.get_room_by_id(room_id)
    return _to_admin_room(room)


@router.patch("/rooms/{room_id}/status", response_model=AdminRoomResponse)
async def admin_update_room_status(
    request: Request, room_id: str, body: RoomStatusUpdate
) -> AdminRoomResponse:
    """Change a room's publication status."""
    validate_uuid(room_id)
    sqlite = request.app.state.sqlite

    if body.status not in ("draft", "published", "featured"):
        raise HTTPException(
            status_code=400,
            detail="Status must be one of: draft, published, featured",
        )

    found = await sqlite.update_room_status(room_id, body.status)
    if not found:
        raise HTTPException(status_code=404, detail="Room not found")

    room = await sqlite.get_room_by_id(room_id)
    return _to_admin_room(room)


@router.delete("/rooms/{room_id}")
async def admin_delete_room(request: Request, room_id: str) -> dict[str, str]:
    """Permanently delete a room."""
    validate_uuid(room_id)
    sqlite = request.app.state.sqlite
    found = await sqlite.delete_room(room_id)
    if not found:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"status": "deleted", "id": room_id}


# ── Runtime Config ──────────────────────────────────────────────────────


@router.get("/config", response_model=RuntimeConfigResponse)
async def admin_get_config(request: Request) -> RuntimeConfigResponse:
    """Get current runtime configuration."""
    settings = request.app.state.settings
    scheduler = getattr(request.app.state, "scheduler", None)
    return RuntimeConfigResponse(
        heartbeat_interval=settings.heartbeat_interval,
        model=settings.model,
        budget_per_cycle=settings.budget.per_cycle,
        budget_daily=settings.budget.daily,
        budget_monthly=settings.budget.monthly,
        temperature_min=settings.creativity.temperature_min,
        temperature_max=settings.creativity.temperature_max,
        novelty_threshold=settings.creativity.novelty_threshold,
        meta_reflection_every=settings.creativity.meta_reflection_every,
        search_provider=settings.search_provider,
        scheduler_running=scheduler is not None and scheduler.running if scheduler else False,
    )


@router.put("/config", response_model=RuntimeConfigResponse)
async def admin_update_config(
    request: Request, body: RuntimeConfigUpdate
) -> RuntimeConfigResponse:
    """Update runtime configuration. Changes take effect on next cycle."""
    settings = request.app.state.settings

    if body.heartbeat_interval is not None:
        settings.heartbeat_interval = body.heartbeat_interval
        # Reschedule if scheduler exists
        scheduler = getattr(request.app.state, "scheduler", None)
        if scheduler and scheduler.running:
            scheduler.reschedule_job(
                "heartbeat", trigger="interval", seconds=body.heartbeat_interval
            )

    if body.model is not None:
        settings.model = body.model
    if body.budget_per_cycle is not None:
        settings.budget.per_cycle = body.budget_per_cycle
    if body.budget_daily is not None:
        settings.budget.daily = body.budget_daily
    if body.budget_monthly is not None:
        settings.budget.monthly = body.budget_monthly
    if body.temperature_min is not None:
        settings.creativity.temperature_min = body.temperature_min
    if body.temperature_max is not None:
        settings.creativity.temperature_max = body.temperature_max
    if body.novelty_threshold is not None:
        settings.creativity.novelty_threshold = body.novelty_threshold
    if body.meta_reflection_every is not None:
        settings.creativity.meta_reflection_every = body.meta_reflection_every

    return await admin_get_config(request)


# ── Scheduler Control ───────────────────────────────────────────────────


@router.post("/scheduler/pause", response_model=SchedulerActionResponse)
async def admin_pause_scheduler(request: Request) -> SchedulerActionResponse:
    """Pause the AI cycle scheduler."""
    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")
    if not scheduler.running:
        return SchedulerActionResponse(status="already_paused", message="Scheduler was already paused")
    scheduler.pause()
    return SchedulerActionResponse(status="paused", message="Scheduler paused")


@router.post("/scheduler/resume", response_model=SchedulerActionResponse)
async def admin_resume_scheduler(request: Request) -> SchedulerActionResponse:
    """Resume the AI cycle scheduler."""
    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")
    scheduler.resume()
    return SchedulerActionResponse(status="resumed", message="Scheduler resumed")


# ── Manual Trigger ──────────────────────────────────────────────────────


@router.post("/trigger", response_model=AdminTriggerResponse)
async def admin_trigger_cycle(request: Request) -> AdminTriggerResponse:
    """Manually trigger an AI cycle (no rate limit for admin)."""
    engine = getattr(request.app.state, "cycle_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="Cycle engine not initialized")

    result = await engine.run_cycle()
    if result.success:
        return AdminTriggerResponse(
            status="ok", message="Cycle completed", room_id=result.room_id
        )
    return AdminTriggerResponse(
        status="error", message=result.error or "Unknown error"
    )


# ── Dashboard ───────────────────────────────────────────────────────────


@router.get("/dashboard")
async def admin_dashboard(request: Request) -> dict[str, Any]:
    """Comprehensive dashboard stats."""
    sqlite = request.app.state.sqlite
    settings = request.app.state.settings
    scheduler = getattr(request.app.state, "scheduler", None)
    registry = getattr(request.app.state, "tool_registry", None)

    import asyncio as _asyncio

    # Run independent queries in parallel
    (total_cost, total_tokens, cost_per_day, total_comments, pending_comments,
     room_counts) = await _asyncio.gather(
        sqlite.get_total_cost(),
        sqlite.get_total_tokens(),
        sqlite.get_cost_per_day(),
        sqlite.count_comments(),
        sqlite.count_comments(status="pending"),
        sqlite.count_rooms_by_status(),
    )

    total_rooms = sum(room_counts.values())
    published = room_counts.get("published", 0)
    featured = room_counts.get("featured", 0)
    drafts = room_counts.get("draft", 0)

    # Extract today's cost from cost_per_day instead of a separate query
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_cost = next((d["cost"] for d in cost_per_day if d["day"] == today), 0.0)

    # Tool usage
    tool_usage = []
    if registry:
        for tool in registry.list_tools():
            tool_usage.append({
                "id": tool.id,
                "name": tool.name,
                "enabled": tool.enabled,
                "daily_usage": registry.get_usage(tool.id),
                "daily_limit": tool.daily_limit,
            })

    return {
        "rooms": {
            "total": total_rooms,
            "published": published,
            "featured": featured,
            "drafts": drafts,
        },
        "costs": {
            "total": round(total_cost, 4),
            "today": round(daily_cost, 4),
            "budget_daily": settings.budget.daily,
            "budget_monthly": settings.budget.monthly,
            "budget_used_pct": round(daily_cost / settings.budget.daily * 100, 1) if settings.budget.daily > 0 else 0,
        },
        "tokens": {
            "total": total_tokens,
        },
        "comments": {
            "total": total_comments,
            "pending": pending_comments,
        },
        "cost_per_day": cost_per_day,
        "tool_usage": tool_usage,
        "scheduler_running": scheduler is not None and scheduler.running if scheduler else False,
        "model": settings.model,
    }


# ── Logs ────────────────────────────────────────────────────────────────


@router.get("/logs")
async def admin_list_logs(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    level: str | None = Query(None),
) -> dict[str, Any]:
    """List cycle logs."""
    sqlite = request.app.state.sqlite
    logs = await sqlite.list_logs(limit=limit, offset=offset, level=level)
    return {"logs": logs}


@router.get("/logs/stream")
async def admin_log_stream(request: Request) -> StreamingResponse:
    """SSE stream for real-time admin logs."""
    import asyncio as _asyncio

    async def event_stream():
        engine = getattr(request.app.state, "cycle_engine", None)
        last_count = 0
        for _ in range(600):  # 10 min max
            if engine and hasattr(engine, "_current_result"):
                result = engine._current_result
                if result and hasattr(result, "logs"):
                    new_logs = result.logs[last_count:]
                    for log in new_logs:
                        yield f"data: {json.dumps({'log': log})}\n\n"
                    last_count = len(result.logs)
            yield f"data: {json.dumps({'heartbeat': True})}\n\n"
            await _asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Comments Admin ──────────────────────────────────────────────────────


@router.get("/comments")
async def admin_list_comments(
    request: Request,
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List all comments with optional status filter."""
    sqlite = request.app.state.sqlite
    comments = await sqlite.list_all_comments(status=status, limit=limit, offset=offset)
    total = await sqlite.count_comments(status=status)
    return {"comments": comments, "total": total}


@router.patch("/comments/{comment_id}/status")
async def admin_update_comment_status(
    request: Request, comment_id: str, body: dict[str, str]
) -> dict[str, str]:
    """Approve or reject a comment."""
    new_status = body.get("status", "")
    if new_status not in ("approved", "rejected", "pending"):
        raise HTTPException(status_code=400, detail="Status must be approved, rejected, or pending")
    sqlite = request.app.state.sqlite
    found = await sqlite.update_comment_status(comment_id, new_status)
    if not found:
        raise HTTPException(status_code=404, detail="Comment not found")
    return {"id": comment_id, "status": new_status}


@router.get("/moderation/config")
async def admin_get_moderation_config(request: Request) -> dict[str, Any]:
    """Get moderation guardrails config."""
    moderator = getattr(request.app.state, "moderator", None)
    if moderator:
        return moderator.config.to_dict()
    return {}


@router.put("/moderation/config")
async def admin_update_moderation_config(
    request: Request, body: dict[str, Any]
) -> dict[str, Any]:
    """Update moderation guardrails."""
    from app.moderation import ModerationConfig, Moderator

    moderator = getattr(request.app.state, "moderator", None)
    if not moderator:
        sqlite = request.app.state.sqlite
        moderator = Moderator(sqlite)
        await moderator.load_config()
        request.app.state.moderator = moderator

    config = moderator.config
    for key, value in body.items():
        if hasattr(config, key):
            setattr(config, key, value)
    await moderator.save_config(config)
    return config.to_dict()


# ── Tool Registry ───────────────────────────────────────────────────────


@router.get("/tools")
async def admin_list_tools(request: Request) -> list[dict[str, Any]]:
    """List all registered tools with daily usage."""
    registry = getattr(request.app.state, "tool_registry", None)
    if not registry:
        return []
    tools = registry.list_tools()
    return [
        {**t.to_dict(), "daily_usage": registry.get_usage(t.id)}
        for t in tools
    ]


@router.put("/tools/{tool_id}")
async def admin_update_tool(
    request: Request, tool_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    """Update a tool's configuration."""
    registry = getattr(request.app.state, "tool_registry", None)
    if not registry:
        raise HTTPException(status_code=503, detail="Tool registry not initialized")
    tool = await registry.update_tool(tool_id, body)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {**tool.to_dict(), "daily_usage": registry.get_usage(tool.id)}


@router.post("/tools")
async def admin_add_tool(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Add a new custom tool."""
    registry = getattr(request.app.state, "tool_registry", None)
    if not registry:
        raise HTTPException(status_code=503, detail="Tool registry not initialized")
    if not body.get("id") or not body.get("name"):
        raise HTTPException(status_code=400, detail="id and name are required")
    tool = await registry.add_tool(body)
    return tool.to_dict()


@router.delete("/tools/{tool_id}")
async def admin_delete_tool(request: Request, tool_id: str) -> dict[str, str]:
    """Remove a custom tool."""
    registry = getattr(request.app.state, "tool_registry", None)
    if not registry:
        raise HTTPException(status_code=503, detail="Tool registry not initialized")
    found = await registry.remove_tool(tool_id)
    if not found:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"status": "deleted", "id": tool_id}


# ── Personality & Guardrails ─────────────────────────────────────────────


@router.get("/personality")
async def admin_get_personality(request: Request) -> dict[str, Any]:
    """Get current personality configuration."""
    from app.personality import load_personality
    sqlite = request.app.state.sqlite
    config = await load_personality(sqlite)
    return config.to_dict()


@router.put("/personality")
async def admin_update_personality(
    request: Request, body: dict[str, Any]
) -> dict[str, Any]:
    """Update personality configuration."""
    from app.personality import load_personality, save_personality
    sqlite = request.app.state.sqlite
    config = await load_personality(sqlite)

    for key in ("seed", "tone_guidelines", "banned_topics"):
        if key in body:
            setattr(config, key, body[key])

    await save_personality(sqlite, config)
    return config.to_dict()


@router.get("/guardrails")
async def admin_get_guardrails(request: Request) -> dict[str, Any]:
    """Get creativity guardrails (temperature, novelty, etc.)."""
    settings = request.app.state.settings
    return {
        "temperature_min": settings.creativity.temperature_min,
        "temperature_max": settings.creativity.temperature_max,
        "novelty_threshold": settings.creativity.novelty_threshold,
        "meta_reflection_every": settings.creativity.meta_reflection_every,
        "wildcard_every": settings.creativity.wildcard_every,
    }


@router.put("/guardrails")
async def admin_update_guardrails(
    request: Request, body: dict[str, Any]
) -> dict[str, Any]:
    """Update creativity guardrails."""
    settings = request.app.state.settings
    c = settings.creativity
    if "temperature_min" in body:
        c.temperature_min = body["temperature_min"]
    if "temperature_max" in body:
        c.temperature_max = body["temperature_max"]
    if "novelty_threshold" in body:
        c.novelty_threshold = body["novelty_threshold"]
    if "meta_reflection_every" in body:
        c.meta_reflection_every = body["meta_reflection_every"]
    if "wildcard_every" in body:
        c.wildcard_every = body["wildcard_every"]
    return await admin_get_guardrails(request)


# ── Helpers ─────────────────────────────────────────────────────────────


def _to_admin_room(room: dict[str, Any]) -> AdminRoomResponse:
    data = parse_room_data(room)
    return AdminRoomResponse(
        id=data.get("id", room.get("id", "")),
        cycle_number=data.get("cycle_number", 0),
        created_at=data.get("created_at", ""),
        title=data.get("title", "Untitled"),
        content_type=data.get("content_type", ""),
        mood=data.get("mood", ""),
        tags=data["tags"],
        total_cost=data.get("total_cost", 0.0),
        has_image=bool(data.get("image_url")),
        has_music=bool(data.get("music_url")),
        status=data.get("status", room.get("status", "published")),
    )
