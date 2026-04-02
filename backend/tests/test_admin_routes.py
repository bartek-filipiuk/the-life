"""Tests for admin API endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin_routes import router as admin_router
from app.config import BudgetConfig, CreativityConfig, Settings
from app.storage.sqlite_store import SQLiteStore

ADMIN_TOKEN = "test-admin-token"
AUTH_HEADER = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

SAMPLE_ROOM = {
    "id": "aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee",
    "cycle_number": 1,
    "created_at": "2026-04-01T12:00:00Z",
    "title": "Test Room",
    "content": "Test content",
    "content_type": "poem",
    "mood": "curious",
    "tags": ["test"],
    "total_cost": 0.05,
    "image_url": None,
    "music_url": None,
    "status": "published",
}


def _create_app() -> FastAPI:
    app = FastAPI()
    app.include_router(admin_router)

    settings = Settings(
        openrouter_api_key="k",
        replicate_api_token="t",
        brave_api_key="b",
        admin_token=ADMIN_TOKEN,
    )
    app.state.settings = settings

    mock_sqlite = MagicMock(spec=SQLiteStore)
    mock_sqlite.count_rooms = AsyncMock(return_value=1)
    mock_sqlite.list_rooms_paginated = AsyncMock(return_value=[SAMPLE_ROOM.copy()])
    mock_sqlite.get_room_by_id = AsyncMock(return_value=SAMPLE_ROOM.copy())
    mock_sqlite.update_room = AsyncMock(return_value=True)
    mock_sqlite.update_room_status = AsyncMock(return_value=True)
    mock_sqlite.delete_room = AsyncMock(return_value=True)
    app.state.sqlite = mock_sqlite
    app.state.scheduler = None
    app.state.cycle_engine = None

    return app


class TestAdminRoomsCRUD:
    def test_list_rooms_all(self):
        app = _create_app()
        client = TestClient(app)
        resp = client.get("/admin/rooms", headers=AUTH_HEADER)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["rooms"]) == 1
        assert data["rooms"][0]["title"] == "Test Room"

    def test_list_rooms_filter_by_status(self):
        app = _create_app()
        client = TestClient(app)
        resp = client.get("/admin/rooms?status=draft", headers=AUTH_HEADER)
        assert resp.status_code == 200
        app.state.sqlite.list_rooms_paginated.assert_called_with(
            page=1, per_page=20, status_filter="draft"
        )

    def test_update_room(self):
        app = _create_app()
        client = TestClient(app)
        resp = client.put(
            f"/admin/rooms/{SAMPLE_ROOM['id']}",
            json={"title": "Updated Title"},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200
        app.state.sqlite.update_room.assert_called_once()

    def test_update_room_no_fields(self):
        app = _create_app()
        client = TestClient(app)
        resp = client.put(
            f"/admin/rooms/{SAMPLE_ROOM['id']}",
            json={},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 400

    def test_update_room_not_found(self):
        app = _create_app()
        app.state.sqlite.update_room = AsyncMock(return_value=False)
        client = TestClient(app)
        resp = client.put(
            f"/admin/rooms/{SAMPLE_ROOM['id']}",
            json={"title": "X"},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 404

    def test_update_room_status(self):
        app = _create_app()
        client = TestClient(app)
        resp = client.patch(
            f"/admin/rooms/{SAMPLE_ROOM['id']}/status",
            json={"status": "featured"},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200
        app.state.sqlite.update_room_status.assert_called_once_with(
            SAMPLE_ROOM["id"], "featured"
        )

    def test_update_room_status_invalid(self):
        app = _create_app()
        client = TestClient(app)
        resp = client.patch(
            f"/admin/rooms/{SAMPLE_ROOM['id']}/status",
            json={"status": "invalid"},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 400

    def test_delete_room(self):
        app = _create_app()
        client = TestClient(app)
        resp = client.delete(
            f"/admin/rooms/{SAMPLE_ROOM['id']}",
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_room_not_found(self):
        app = _create_app()
        app.state.sqlite.delete_room = AsyncMock(return_value=False)
        client = TestClient(app)
        resp = client.delete(
            f"/admin/rooms/{SAMPLE_ROOM['id']}",
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 404

    def test_invalid_uuid_rejected(self):
        app = _create_app()
        client = TestClient(app)
        resp = client.delete("/admin/rooms/not-a-uuid", headers=AUTH_HEADER)
        assert resp.status_code == 400


class TestAdminConfig:
    def test_get_config(self):
        app = _create_app()
        client = TestClient(app)
        resp = client.get("/admin/config", headers=AUTH_HEADER)
        assert resp.status_code == 200
        data = resp.json()
        assert data["heartbeat_interval"] == 3600
        assert data["model"] == "openai/gpt-5.4"
        assert data["budget_daily"] == 20.0
        assert data["scheduler_running"] is False

    def test_update_config(self):
        app = _create_app()
        client = TestClient(app)
        resp = client.put(
            "/admin/config",
            json={"model": "anthropic/claude-4", "budget_daily": 50.0},
            headers=AUTH_HEADER,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == "anthropic/claude-4"
        assert data["budget_daily"] == 50.0


class TestAdminScheduler:
    def test_pause_no_scheduler(self):
        app = _create_app()
        client = TestClient(app)
        resp = client.post("/admin/scheduler/pause", headers=AUTH_HEADER)
        assert resp.status_code == 503

    def test_pause_and_resume(self):
        app = _create_app()
        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_scheduler.pause = MagicMock()
        mock_scheduler.resume = MagicMock()
        app.state.scheduler = mock_scheduler

        client = TestClient(app)
        resp = client.post("/admin/scheduler/pause", headers=AUTH_HEADER)
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"
        mock_scheduler.pause.assert_called_once()

        resp = client.post("/admin/scheduler/resume", headers=AUTH_HEADER)
        assert resp.status_code == 200
        assert resp.json()["status"] == "resumed"
        mock_scheduler.resume.assert_called_once()


class TestAdminTrigger:
    def test_trigger_no_engine(self):
        app = _create_app()
        client = TestClient(app)
        resp = client.post("/admin/trigger", headers=AUTH_HEADER)
        assert resp.status_code == 503

    def test_trigger_success(self):
        app = _create_app()
        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.room_id = "new-room-id"
        mock_engine.run_cycle = AsyncMock(return_value=mock_result)
        app.state.cycle_engine = mock_engine

        client = TestClient(app)
        resp = client.post("/admin/trigger", headers=AUTH_HEADER)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["room_id"] == "new-room-id"
