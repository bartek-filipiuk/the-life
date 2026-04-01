"""Pydantic response models for the REST API."""

from __future__ import annotations

from pydantic import BaseModel


class RoomResponse(BaseModel):
    id: str
    cycle_number: int
    created_at: str
    title: str
    content: str
    content_type: str
    mood: str
    tags: list[str]
    image_url: str | None = None
    image_prompt: str | None = None
    music_url: str | None = None
    music_prompt: str | None = None
    intention: str = ""
    reasoning: str = ""
    search_queries: list[str] = []
    search_results: list[dict] = []
    next_hint: str = ""
    connections: list[str] = []
    model: str = ""
    llm_tokens: int = 0
    llm_cost: float = 0.0
    image_cost: float = 0.0
    music_cost: float = 0.0
    search_cost: float = 0.0
    total_cost: float = 0.0
    duration_ms: int = 0


class RoomSummary(BaseModel):
    id: str
    cycle_number: int
    created_at: str
    title: str
    content_type: str
    mood: str
    tags: list[str]
    total_cost: float = 0.0
    has_image: bool = False
    has_music: bool = False


class GraphNode(BaseModel):
    id: str
    label: str
    content_type: str
    mood: str
    tags: list[str]
    cycle_number: int
    size: int = 1  # connection count


class GraphEdge(BaseModel):
    source: str
    target: str


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class StatsResponse(BaseModel):
    total_rooms: int = 0
    total_cost: float = 0.0
    total_tokens: int = 0
    avg_cost_per_room: float = 0.0
    cost_per_day: list[dict] = []
    model: str = ""
    uptime_days: int = 0


class TimelineDayResponse(BaseModel):
    date: str
    rooms: list[RoomSummary]


class TimelineResponse(BaseModel):
    days: list[TimelineDayResponse]


class HealthResponse(BaseModel):
    status: str = "ok"
    cycle_count: int = 0
    next_cycle_in: int = 0  # seconds


class TriggerResponse(BaseModel):
    status: str
    message: str
    room_id: str | None = None


class PaginatedRooms(BaseModel):
    rooms: list[RoomSummary]
    total: int
    page: int
    per_page: int
