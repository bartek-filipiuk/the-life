"""Pydantic models for admin API endpoints."""

from __future__ import annotations

from pydantic import BaseModel

from app.api.schemas import RoomSummary, TriggerResponse


class RoomStatusUpdate(BaseModel):
    status: str


class RoomUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    content_type: str | None = None
    mood: str | None = None
    tags: list[str] | None = None
    status: str | None = None


class AdminRoomResponse(RoomSummary):
    status: str = "published"


class AdminRoomListResponse(BaseModel):
    rooms: list[AdminRoomResponse]
    total: int
    page: int
    per_page: int


class RuntimeConfigResponse(BaseModel):
    heartbeat_interval: int
    model: str
    budget_per_cycle: float
    budget_daily: float
    budget_monthly: float
    temperature_min: float
    temperature_max: float
    novelty_threshold: float
    meta_reflection_every: int
    search_provider: str
    scheduler_running: bool = False


class RuntimeConfigUpdate(BaseModel):
    heartbeat_interval: int | None = None
    model: str | None = None
    budget_per_cycle: float | None = None
    budget_daily: float | None = None
    budget_monthly: float | None = None
    temperature_min: float | None = None
    temperature_max: float | None = None
    novelty_threshold: float | None = None
    meta_reflection_every: int | None = None


class SchedulerActionResponse(BaseModel):
    status: str
    message: str


AdminTriggerResponse = TriggerResponse
