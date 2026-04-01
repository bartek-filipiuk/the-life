"""Tests for REST API endpoints."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.routes import router, _last_trigger_time
from app.api.schemas import HealthResponse
from app.storage.sqlite_store import SQLiteStore


def _create_test_app():
    """Create a minimal FastAPI app for testing (no lifespan)."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    app.include_router(router)
    return app


@pytest.fixture
def app_with_data():
    """Create test app with mock sqlite data."""
    app = _create_test_app()

    mock_sqlite = MagicMock(spec=SQLiteStore)
    mock_sqlite.count_rooms = AsyncMock(return_value=5)
    mock_sqlite.total_cost = AsyncMock(return_value=1.23)
    mock_sqlite.total_tokens = AsyncMock(return_value=5000)
    mock_sqlite.cost_per_day = AsyncMock(return_value=[{"day": "2026-04-01", "cost": 1.23}])
    mock_sqlite.list_paginated = AsyncMock(return_value=[
        {"id": "test-id", "data": json.dumps({
            "id": "test-id", "cycle_number": 1, "created_at": "2026-04-01T12:00:00Z",
            "title": "Test Room", "content_type": "poem", "mood": "curious",
            "tags": ["test"], "total_cost": 0.05,
        })},
    ])
    mock_sqlite.get_by_id = AsyncMock(return_value={
        "id": "aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee",
        "data": json.dumps({
            "id": "aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee",
            "cycle_number": 1, "created_at": "2026-04-01T12:00:00Z",
            "title": "Test Room", "content": "A poem", "content_type": "poem",
            "mood": "curious", "tags": ["test"],
        }),
    })
    mock_sqlite.list_by_day = AsyncMock(return_value=[])

    mock_settings = MagicMock()
    mock_settings.model = "test/model"

    app.state.sqlite = mock_sqlite
    app.state.settings = mock_settings
    app.state.cycle_engine = None

    return app


@pytest.fixture
def client(app_with_data):
    return TestClient(app_with_data)


class TestHealth:
    def test_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["cycle_count"] == 5


class TestListRooms:
    def test_returns_paginated(self, client):
        response = client.get("/rooms")
        assert response.status_code == 200
        data = response.json()
        assert "rooms" in data
        assert data["total"] == 5
        assert data["page"] == 1

    def test_pagination_params(self, client):
        response = client.get("/rooms?page=2&per_page=10")
        assert response.status_code == 200

    def test_invalid_page(self, client):
        response = client.get("/rooms?page=0")
        assert response.status_code == 422  # validation error

    def test_per_page_limit(self, client):
        response = client.get("/rooms?per_page=200")
        assert response.status_code == 422  # exceeds 100


class TestGetRoom:
    def test_returns_room(self, client):
        response = client.get("/rooms/aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Room"

    def test_invalid_uuid(self, client):
        response = client.get("/rooms/not-a-uuid")
        assert response.status_code == 400

    def test_not_found(self, client, app_with_data):
        app_with_data.state.sqlite.get_by_id = AsyncMock(return_value=None)
        response = client.get("/rooms/aaaaaaaa-bbbb-4ccc-dddd-ffffffffffff")
        assert response.status_code == 404


class TestGraph:
    def test_returns_graph(self, client):
        response = client.get("/graph")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data


class TestStats:
    def test_returns_stats(self, client):
        response = client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_rooms"] == 5
        assert data["total_cost"] == 1.23
        assert data["total_tokens"] == 5000


class TestTimeline:
    def test_returns_timeline(self, client):
        response = client.get("/timeline")
        assert response.status_code == 200
        data = response.json()
        assert "days" in data


class TestTrigger:
    def test_rate_limited(self, client):
        import app.api.routes as routes_mod
        routes_mod._last_trigger_time = 0.0

        # First call — no engine → 503
        response = client.post("/trigger")
        assert response.status_code == 503

        # Second call immediately — rate limited
        response = client.post("/trigger")
        assert response.status_code == 429

    def test_no_engine(self, client):
        import app.api.routes as routes_mod
        routes_mod._last_trigger_time = 0.0
        response = client.post("/trigger")
        assert response.status_code == 503


class TestSecurityHeaders:
    def test_has_security_headers(self, client):
        response = client.get("/health")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"


class TestCORS:
    def test_cors_allowed_origin(self, client):
        response = client.options(
            "/health",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_cors_disallowed_origin(self, client):
        response = client.options(
            "/health",
            headers={"Origin": "http://evil.com", "Access-Control-Request-Method": "GET"},
        )
        assert response.headers.get("access-control-allow-origin") != "http://evil.com"
