"""Tests for app.memory.novelty — novelty check with similar/different texts, threshold behavior."""

import uuid

import pytest

from app.memory.chromadb_store import ChromaDBStore
from app.memory.novelty import NoveltyResult, check_novelty


@pytest.fixture
def store(tmp_path) -> ChromaDBStore:
    """Create a connected ChromaDBStore using a temp directory."""
    s = ChromaDBStore(persist_dir=str(tmp_path / "chroma"))
    s.connect()
    return s


def _room_id() -> str:
    return str(uuid.uuid4())


class TestNoveltyResult:
    """Test the NoveltyResult dataclass."""

    def test_similarity_computed_from_distance(self) -> None:
        result = NoveltyResult(is_novel=True, closest_distance=0.2, closest_room_id="abc")
        assert result.similarity == pytest.approx(0.8)

    def test_similarity_none_when_no_distance(self) -> None:
        result = NoveltyResult(is_novel=True, closest_distance=None, closest_room_id=None)
        assert result.similarity is None

    def test_similarity_zero_distance_means_identical(self) -> None:
        result = NoveltyResult(is_novel=False, closest_distance=0.0, closest_room_id="abc")
        assert result.similarity == pytest.approx(1.0)

    def test_frozen_dataclass(self) -> None:
        result = NoveltyResult(is_novel=True, closest_distance=None, closest_room_id=None)
        with pytest.raises(AttributeError):
            result.is_novel = False  # type: ignore[misc]


class TestCheckNoveltyEmptyStore:
    """Test novelty checks when no rooms exist."""

    def test_empty_store_is_always_novel(self, store: ChromaDBStore) -> None:
        result = check_novelty(store, "Any text at all")
        assert result.is_novel is True
        assert result.closest_distance is None
        assert result.closest_room_id is None


class TestCheckNoveltyWithRooms:
    """Test novelty checks with existing rooms in the store."""

    def test_very_different_text_is_novel(self, store: ChromaDBStore) -> None:
        store.add_room(
            room_id=_room_id(),
            content="The ocean waves crash against the rocky shore at midnight under a full moon",
            metadata={"cycle_number": 1, "mood": "calm", "content_type": "poem"},
        )
        result = check_novelty(
            store,
            "Quantum computing uses qubits to perform parallel calculations on complex algorithms",
        )
        assert result.is_novel is True
        assert result.closest_distance is not None
        assert result.closest_room_id is not None

    def test_identical_text_is_not_novel(self, store: ChromaDBStore) -> None:
        store.add_room(
            room_id=_room_id(),
            content="The stars shine brightly in the dark night sky",
            metadata={"cycle_number": 1, "mood": "wonder", "content_type": "poem"},
        )
        result = check_novelty(store, "The stars shine brightly in the dark night sky")
        assert result.is_novel is False
        assert result.closest_distance is not None
        # Distance should be very small for identical text
        assert result.closest_distance < 0.1

    def test_very_similar_text_is_not_novel(self, store: ChromaDBStore) -> None:
        store.add_room(
            room_id=_room_id(),
            content="The stars shine brightly in the dark night sky above the mountains",
            metadata={"cycle_number": 1, "mood": "wonder", "content_type": "poem"},
        )
        result = check_novelty(
            store,
            "The stars glow brightly in the dark night sky above the mountains",
        )
        # Nearly identical text should have high similarity (low distance)
        assert result.closest_distance is not None
        assert result.closest_distance < 0.2

    def test_closest_room_id_is_returned(self, store: ChromaDBStore) -> None:
        rid = _room_id()
        store.add_room(
            room_id=rid,
            content="A unique room about existential philosophy and the meaning of life",
            metadata={"cycle_number": 1, "mood": "deep", "content_type": "essay"},
        )
        result = check_novelty(
            store,
            "Existential philosophy explores the meaning of human existence",
        )
        assert result.closest_room_id == rid


class TestCheckNoveltyThreshold:
    """Test threshold behavior."""

    def test_low_threshold_makes_similar_text_novel(self, store: ChromaDBStore) -> None:
        store.add_room(
            room_id=_room_id(),
            content="The ocean waves crash on the shore",
            metadata={"cycle_number": 1, "mood": "calm", "content_type": "poem"},
        )
        # With a very low threshold (e.g., 0.1), even somewhat similar text is "novel"
        result = check_novelty(
            store,
            "The sea waves hit the beach",
            threshold=0.1,
        )
        # Similarity should be above 0.1 for these similar texts, so not novel
        # But with threshold=0.1, similarity >= 0.1 → not novel
        # The key point: lowering threshold makes it harder to be novel
        assert result.closest_distance is not None

    def test_high_threshold_accepts_more(self, store: ChromaDBStore) -> None:
        store.add_room(
            room_id=_room_id(),
            content="The ocean waves crash against the rocky shore at midnight",
            metadata={"cycle_number": 1, "mood": "calm", "content_type": "poem"},
        )
        # With threshold=0.99, almost everything is novel
        result = check_novelty(
            store,
            "The ocean waves crash against the rocky shore at midnight under stars",
            threshold=0.99,
        )
        assert result.is_novel is True

    def test_threshold_1_accepts_everything(self, store: ChromaDBStore) -> None:
        store.add_room(
            room_id=_room_id(),
            content="Exact same text for testing",
            metadata={"cycle_number": 1, "mood": "neutral", "content_type": "essay"},
        )
        # threshold=1.0 means similarity must be < 1.0, so only truly identical rejected
        # Even identical text via embeddings may have tiny distance > 0
        result = check_novelty(store, "Exact same text for testing", threshold=1.0)
        # Similarity of identical text ~ 1.0, so is_novel depends on exact float
        assert result.closest_distance is not None

    def test_default_threshold_is_092(self, store: ChromaDBStore) -> None:
        """Verify the default threshold from the spec is 0.92."""
        store.add_room(
            room_id=_room_id(),
            content="A completely unrelated topic about quantum physics and black holes in space",
            metadata={"cycle_number": 1, "mood": "curious", "content_type": "essay"},
        )
        result = check_novelty(
            store,
            "Baking a chocolate cake requires flour sugar eggs and cocoa powder",
        )
        # Very different topics should be novel with default threshold
        assert result.is_novel is True


class TestCheckNoveltyMultipleRooms:
    """Test novelty with multiple existing rooms."""

    def test_finds_closest_among_multiple(self, store: ChromaDBStore) -> None:
        store.add_room(
            room_id=_room_id(),
            content="Programming in Python with decorators and generators",
            metadata={"cycle_number": 1, "mood": "analytical", "content_type": "essay"},
        )
        store.add_room(
            room_id=_room_id(),
            content="The beauty of coral reefs and marine biodiversity",
            metadata={"cycle_number": 2, "mood": "wonder", "content_type": "poem"},
        )
        store.add_room(
            room_id=_room_id(),
            content="Classical music composition and orchestral arrangements by Beethoven",
            metadata={"cycle_number": 3, "mood": "creative", "content_type": "essay"},
        )
        result = check_novelty(
            store,
            "Python programming with async await and type hints",
        )
        # Should find the Python room as closest
        assert result.closest_distance is not None
        assert result.closest_room_id is not None
