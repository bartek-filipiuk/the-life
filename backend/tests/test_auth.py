"""Tests for admin authentication middleware."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin_routes import router as admin_router
from app.config import Settings
from app.storage.sqlite_store import SQLiteStore


def _create_admin_test_app(admin_token: str = "test-secret-token") -> FastAPI:
    """Create a minimal FastAPI app with admin routes for testing."""
    app = FastAPI()
    app.include_router(admin_router)

    settings = Settings(
        openrouter_api_key="test-key",
        replicate_api_token="test-token",
        brave_api_key="test-brave",
        admin_token=admin_token,
    )
    app.state.settings = settings

    mock_sqlite = MagicMock(spec=SQLiteStore)
    mock_sqlite.count_rooms = AsyncMock(return_value=3)
    mock_sqlite.list_rooms_paginated = AsyncMock(return_value=[])
    app.state.sqlite = mock_sqlite
    app.state.scheduler = None
    app.state.cycle_engine = None

    return app


class TestAuthMiddleware:
    def test_valid_token_allows_access(self):
        app = _create_admin_test_app()
        client = TestClient(app)
        resp = client.get(
            "/admin/rooms",
            headers={"Authorization": "Bearer test-secret-token"},
        )
        assert resp.status_code == 200

    def test_missing_token_returns_401(self):
        app = _create_admin_test_app()
        client = TestClient(app)
        resp = client.get("/admin/rooms")
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self):
        app = _create_admin_test_app()
        client = TestClient(app)
        resp = client.get(
            "/admin/rooms",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    def test_empty_admin_token_config_returns_503(self):
        app = _create_admin_test_app(admin_token="")
        client = TestClient(app)
        resp = client.get(
            "/admin/rooms",
            headers={"Authorization": "Bearer anything"},
        )
        assert resp.status_code == 503

    def test_bearer_scheme_required(self):
        app = _create_admin_test_app()
        client = TestClient(app)
        resp = client.get(
            "/admin/rooms",
            headers={"Authorization": "Basic dGVzdDp0ZXN0"},
        )
        assert resp.status_code == 401
