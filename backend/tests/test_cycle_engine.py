"""Tests for the AI Cycle Engine — mocks all dependencies."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import BudgetConfig, CreativityConfig, Settings, StorageConfig
from app.cycle_engine import CycleEngine, CycleResult
from app.llm_client import LLMClient, LLMResponse, LLMUsage
from app.memory.chromadb_store import ChromaDBStore
from app.storage.sqlite_store import SQLiteStore


@pytest.fixture
def settings():
    return Settings(
        openrouter_api_key="test-key",
        replicate_api_token="test-token",
        brave_api_key="test-brave",
        model="test/model",
        budget=BudgetConfig(per_cycle=2.0, daily=20.0, monthly=300.0),
        creativity=CreativityConfig(
            temperature_min=0.7, temperature_max=1.0,
            novelty_threshold=0.92, meta_reflection_every=10, wildcard_every=5,
        ),
        storage=StorageConfig(data_dir="./data", chromadb_dir="./data/chromadb", sqlite_path="./data/test.db"),
    )


@pytest.fixture
def mock_llm():
    llm = MagicMock(spec=LLMClient)
    # Decision call returns structured JSON
    decision_json = {
        "intention": "explore the beauty of mathematics",
        "mood": "curious",
        "tools_to_use": ["web_search"],
        "search_queries": ["fibonacci in nature"],
        "image_prompt": None,
        "music_prompt": None,
        "reasoning": "Math reveals hidden patterns",
    }
    llm.decision_call = AsyncMock(return_value=LLMResponse(
        content=json.dumps(decision_json),
        parsed_json=decision_json,
        usage=LLMUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150, model="test"),
    ))
    # Creation call returns room content
    room_json = {
        "title": "Fibonacci Dreams",
        "content": "In spirals of golden ratio, nature speaks...",
        "content_type": "poem",
        "tags": ["mathematics", "nature", "beauty"],
        "connections": [],
        "next_direction_hint": "explore fractals",
        "meta_note": "math is beautiful",
    }
    llm.creation_call = AsyncMock(return_value=LLMResponse(
        content=json.dumps(room_json),
        parsed_json=room_json,
        usage=LLMUsage(prompt_tokens=200, completion_tokens=100, total_tokens=300, model="test"),
    ))
    return llm


@pytest.fixture
def mock_chromadb():
    store = MagicMock(spec=ChromaDBStore)
    store.connect = MagicMock()
    store.query_recent.return_value = []
    store.query_similar.return_value = []
    store.query_arcs.return_value = []
    store.room_count.return_value = 0
    store.arc_count.return_value = 0
    store.add_room = MagicMock()
    store.add_arc = MagicMock()
    store.add_search_result = MagicMock()
    return store


@pytest.fixture
def mock_sqlite():
    store = MagicMock(spec=SQLiteStore)
    store.count_rooms = AsyncMock(return_value=0)
    store.get_daily_cost = AsyncMock(return_value=0.0)
    store.insert_room = AsyncMock()
    store.get_config = AsyncMock(return_value=None)
    store.get_recent_approved_comments = AsyncMock(return_value=[])
    return store


@pytest.fixture
def engine(settings, mock_llm, mock_chromadb, mock_sqlite):
    with tempfile.TemporaryDirectory() as tmpdir:
        yield CycleEngine(
            settings=settings,
            llm=mock_llm,
            chromadb=mock_chromadb,
            sqlite=mock_sqlite,
            data_dir=Path(tmpdir),
        )


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_full_cycle(self, engine, mock_llm, mock_chromadb, mock_sqlite):
        with patch("app.cycle_engine.check_novelty") as mock_novelty:
            mock_novelty.return_value = MagicMock(is_novel=True)

            result = await engine.run_cycle()

        assert result.success is True
        assert result.cycle_number == 1
        assert result.room_data["title"] == "Fibonacci Dreams"
        assert result.llm_tokens == 450  # 150 + 300
        assert mock_sqlite.insert_room.called
        assert mock_chromadb.add_room.called

    @pytest.mark.asyncio
    async def test_cycle_number_increments(self, engine, mock_sqlite):
        mock_sqlite.count_rooms = AsyncMock(return_value=5)

        with patch("app.cycle_engine.check_novelty") as mock_novelty:
            mock_novelty.return_value = MagicMock(is_novel=True)
            result = await engine.run_cycle()

        assert result.cycle_number == 6


class TestBudgetExhausted:
    @pytest.mark.asyncio
    async def test_skips_cycle_when_budget_exhausted(self, engine, mock_sqlite):
        mock_sqlite.get_daily_cost = AsyncMock(return_value=20.0)  # equals daily budget

        result = await engine.run_cycle()

        assert result.success is False
        assert result.error == "Daily budget exhausted"


class TestToolFailureGracefulDegradation:
    @pytest.mark.asyncio
    async def test_continues_when_search_fails(self, engine, mock_llm):
        # Decision wants web search
        decision_json = {
            "intention": "test", "mood": "curious",
            "tools_to_use": ["web_search"],
            "search_queries": ["failing query"],
            "reasoning": "test",
        }
        mock_llm.decision_call = AsyncMock(return_value=LLMResponse(
            content=json.dumps(decision_json),
            parsed_json=decision_json,
            usage=LLMUsage(total_tokens=100),
        ))

        # Mock the search provider to fail
        from app.tools.search_provider import SearchProviderError
        mock_search = MagicMock()
        mock_search.search = AsyncMock(side_effect=SearchProviderError("API down"))
        engine._search = mock_search

        with patch("app.cycle_engine.check_novelty") as mock_novelty:
            mock_novelty.return_value = MagicMock(is_novel=True)
            result = await engine.run_cycle()

        # Cycle should still succeed despite search failure
        assert result.success is True
        assert result.search_results == []


class TestNoveltyRetry:
    @pytest.mark.asyncio
    async def test_retries_on_too_similar(self, engine, mock_llm):
        with patch("app.cycle_engine.check_novelty") as mock_novelty:
            # First check: not novel. After retry: novel (auto from mock)
            mock_novelty.return_value = MagicMock(is_novel=False, closest_distance=0.05)

            result = await engine.run_cycle()

        # creation_call should be called twice (original + retry)
        assert mock_llm.creation_call.call_count == 2


class TestMetaReflection:
    @pytest.mark.asyncio
    async def test_triggers_at_correct_interval(self, engine, mock_sqlite, mock_chromadb, mock_llm):
        mock_sqlite.count_rooms = AsyncMock(return_value=9)  # cycle 10 triggers reflection
        mock_chromadb.query_recent.return_value = [
            {"metadata": {"title": f"Room {i}", "content_type": "poem", "mood": "curious"}, "document": f"content {i}"}
            for i in range(10)
        ]

        # Mock the reflection LLM call
        reflection_json = {
            "arc_summary": "A journey through math and nature",
            "blind_spots": "Haven't explored music yet",
            "next_arc_direction": "explore sound and rhythm",
        }
        # The creation_call is used for both room creation and reflection
        mock_llm.creation_call = AsyncMock(return_value=LLMResponse(
            content=json.dumps(reflection_json),
            parsed_json=reflection_json,
            usage=LLMUsage(total_tokens=100),
        ))

        with patch("app.cycle_engine.check_novelty") as mock_novelty:
            mock_novelty.return_value = MagicMock(is_novel=True)
            result = await engine.run_cycle()

        assert result.cycle_number == 10
        # Arc should be added
        assert mock_chromadb.add_arc.called


class TestLogging:
    @pytest.mark.asyncio
    async def test_cycle_produces_logs(self, engine):
        with patch("app.cycle_engine.check_novelty") as mock_novelty:
            mock_novelty.return_value = MagicMock(is_novel=True)
            result = await engine.run_cycle()

        assert len(result.logs) > 0
        assert any("[CYCLE]" in log for log in result.logs)
        assert any("[DONE]" in log for log in result.logs)
