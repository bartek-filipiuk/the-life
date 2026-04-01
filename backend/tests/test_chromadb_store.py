"""Tests for app.memory.chromadb_store — add/query rooms, similarity search, collections."""

import uuid

import pytest

from app.memory.chromadb_store import ChromaDBStore, _sanitize_metadata


@pytest.fixture
def store(tmp_path) -> ChromaDBStore:
    """Create a connected ChromaDBStore using a temp directory."""
    s = ChromaDBStore(persist_dir=str(tmp_path / "chroma"))
    s.connect()
    return s


def _room_id() -> str:
    return str(uuid.uuid4())


class TestConnection:
    """Test connect/disconnect behavior."""

    def test_not_connected_raises(self, tmp_path) -> None:
        s = ChromaDBStore(persist_dir=str(tmp_path / "chroma"))
        with pytest.raises(RuntimeError, match="not connected"):
            _ = s.rooms

    def test_not_connected_arcs_raises(self, tmp_path) -> None:
        s = ChromaDBStore(persist_dir=str(tmp_path / "chroma"))
        with pytest.raises(RuntimeError, match="not connected"):
            _ = s.arcs

    def test_not_connected_search_raises(self, tmp_path) -> None:
        s = ChromaDBStore(persist_dir=str(tmp_path / "chroma"))
        with pytest.raises(RuntimeError, match="not connected"):
            _ = s.search

    def test_connect_creates_collections(self, store: ChromaDBStore) -> None:
        assert store.rooms is not None
        assert store.arcs is not None
        assert store.search is not None


class TestAddAndQueryRooms:
    """Test room add/query operations."""

    def test_add_room_increments_count(self, store: ChromaDBStore) -> None:
        assert store.room_count() == 0
        store.add_room(
            room_id=_room_id(),
            content="A poem about stars and the void",
            metadata={"mood": "contemplative", "content_type": "poem", "cycle_number": 1},
        )
        assert store.room_count() == 1

    def test_add_multiple_rooms(self, store: ChromaDBStore) -> None:
        for i in range(3):
            store.add_room(
                room_id=_room_id(),
                content=f"Room content {i}",
                metadata={"cycle_number": i + 1, "mood": "neutral", "content_type": "essay"},
            )
        assert store.room_count() == 3

    def test_get_room_by_id(self, store: ChromaDBStore) -> None:
        rid = _room_id()
        store.add_room(
            room_id=rid,
            content="Test room content",
            metadata={"mood": "happy", "content_type": "poem", "cycle_number": 1},
        )
        result = store.get_room(rid)
        assert result is not None
        assert result["id"] == rid
        assert result["document"] == "Test room content"
        assert result["metadata"]["mood"] == "happy"

    def test_get_nonexistent_room(self, store: ChromaDBStore) -> None:
        result = store.get_room(_room_id())
        assert result is None

    def test_upsert_updates_existing(self, store: ChromaDBStore) -> None:
        rid = _room_id()
        store.add_room(
            room_id=rid,
            content="Original content",
            metadata={"cycle_number": 1, "mood": "sad", "content_type": "poem"},
        )
        store.add_room(
            room_id=rid,
            content="Updated content",
            metadata={"cycle_number": 1, "mood": "happy", "content_type": "essay"},
        )
        assert store.room_count() == 1
        result = store.get_room(rid)
        assert result["document"] == "Updated content"
        assert result["metadata"]["mood"] == "happy"


class TestQueryRecent:
    """Test query_recent method."""

    def test_empty_collection(self, store: ChromaDBStore) -> None:
        assert store.query_recent() == []

    def test_returns_rooms(self, store: ChromaDBStore) -> None:
        for i in range(3):
            store.add_room(
                room_id=_room_id(),
                content=f"Content for cycle {i + 1}",
                metadata={"cycle_number": i + 1, "mood": "neutral", "content_type": "essay"},
            )
        results = store.query_recent(n=2)
        assert len(results) <= 2

    def test_respects_n_limit(self, store: ChromaDBStore) -> None:
        for i in range(5):
            store.add_room(
                room_id=_room_id(),
                content=f"Content {i}",
                metadata={"cycle_number": i + 1, "mood": "neutral", "content_type": "essay"},
            )
        results = store.query_recent(n=3)
        assert len(results) <= 3


class TestQuerySimilar:
    """Test similarity search."""

    def test_empty_collection(self, store: ChromaDBStore) -> None:
        assert store.query_similar("anything") == []

    def test_returns_results_with_distance(self, store: ChromaDBStore) -> None:
        store.add_room(
            room_id=_room_id(),
            content="The ocean waves crash against the shore at midnight",
            metadata={"cycle_number": 1, "mood": "calm", "content_type": "poem"},
        )
        store.add_room(
            room_id=_room_id(),
            content="Binary code and algorithms define modern computing",
            metadata={"cycle_number": 2, "mood": "analytical", "content_type": "essay"},
        )
        results = store.query_similar("sea and water and beach waves", n=2)
        assert len(results) == 2
        assert "distance" in results[0]
        assert isinstance(results[0]["distance"], float)

    def test_similar_text_ranked_first(self, store: ChromaDBStore) -> None:
        store.add_room(
            room_id=_room_id(),
            content="Stars shimmer in the dark night sky above the mountains",
            metadata={"cycle_number": 1, "mood": "wonder", "content_type": "poem"},
        )
        store.add_room(
            room_id=_room_id(),
            content="Financial markets showed strong growth in Q2 earnings",
            metadata={"cycle_number": 2, "mood": "neutral", "content_type": "essay"},
        )
        results = store.query_similar("the cosmos and starlight twinkling above", n=2)
        # The space/stars content should be more similar than finance content
        assert "star" in results[0]["document"].lower() or "sky" in results[0]["document"].lower()

    def test_n_capped_to_collection_size(self, store: ChromaDBStore) -> None:
        store.add_room(
            room_id=_room_id(),
            content="Only room",
            metadata={"cycle_number": 1, "mood": "lonely", "content_type": "haiku"},
        )
        results = store.query_similar("test query", n=10)
        assert len(results) == 1


class TestJourneyArcs:
    """Test arc add/query."""

    def test_add_arc(self, store: ChromaDBStore) -> None:
        assert store.arc_count() == 0
        store.add_arc(
            arc_id=_room_id(),
            summary="An arc exploring themes of consciousness and identity",
            metadata={"start_cycle": 1, "end_cycle": 10, "themes": "consciousness,identity"},
        )
        assert store.arc_count() == 1

    def test_query_arcs_empty(self, store: ChromaDBStore) -> None:
        assert store.query_arcs("anything") == []

    def test_query_arcs_returns_results(self, store: ChromaDBStore) -> None:
        store.add_arc(
            arc_id=_room_id(),
            summary="Exploring the nature of creativity and art",
            metadata={"start_cycle": 1, "end_cycle": 5, "themes": "creativity,art"},
        )
        store.add_arc(
            arc_id=_room_id(),
            summary="Investigating quantum physics and reality",
            metadata={"start_cycle": 6, "end_cycle": 10, "themes": "physics,reality"},
        )
        results = store.query_arcs("artistic expression and painting", n=2)
        assert len(results) == 2
        assert "distance" in results[0]


class TestSearchCache:
    """Test search cache add/query."""

    def test_add_search_result(self, store: ChromaDBStore) -> None:
        assert store.search_count() == 0
        store.add_search_result(
            search_id=_room_id(),
            query="latest discoveries in astronomy",
            metadata={"query": "latest discoveries in astronomy", "source_url": "https://example.com"},
        )
        assert store.search_count() == 1

    def test_query_search_cache_empty(self, store: ChromaDBStore) -> None:
        assert store.query_search_cache("anything") == []

    def test_query_search_cache_returns_results(self, store: ChromaDBStore) -> None:
        store.add_search_result(
            search_id=_room_id(),
            query="climate change effects on oceans",
            metadata={"query": "climate change effects on oceans", "source_url": "https://example.com/1"},
        )
        store.add_search_result(
            search_id=_room_id(),
            query="best programming languages 2026",
            metadata={"query": "best programming languages 2026", "source_url": "https://example.com/2"},
        )
        results = store.query_search_cache("global warming and sea level rise", n=2)
        assert len(results) == 2


class TestSanitizeMetadata:
    """Test the _sanitize_metadata helper."""

    def test_passes_through_primitives(self) -> None:
        meta = {"name": "test", "count": 42, "score": 0.95, "active": True}
        result = _sanitize_metadata(meta)
        assert result == meta

    def test_joins_lists(self) -> None:
        meta = {"tags": ["ai", "music", "art"]}
        result = _sanitize_metadata(meta)
        assert result["tags"] == "ai,music,art"

    def test_skips_none_values(self) -> None:
        meta = {"key": "value", "empty": None}
        result = _sanitize_metadata(meta)
        assert "empty" not in result
        assert result["key"] == "value"

    def test_casts_other_types_to_str(self) -> None:
        meta = {"data": {"nested": "dict"}}
        result = _sanitize_metadata(meta)
        assert isinstance(result["data"], str)
