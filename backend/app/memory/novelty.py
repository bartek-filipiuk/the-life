"""Novelty checking via ChromaDB embedding similarity.

Embeds text using ChromaDB's default embedding function and compares
cosine similarity against existing rooms. Returns whether the text
is novel enough (below the similarity threshold).
"""

from dataclasses import dataclass

from app.memory.chromadb_store import ChromaDBStore


@dataclass(frozen=True)
class NoveltyResult:
    """Result of a novelty check."""

    is_novel: bool
    closest_distance: float | None
    closest_room_id: str | None

    @property
    def similarity(self) -> float | None:
        """Cosine similarity (1 - distance) to the closest match.

        Returns None if no existing rooms to compare against.
        """
        if self.closest_distance is None:
            return None
        return 1.0 - self.closest_distance


def check_novelty(
    store: ChromaDBStore,
    text: str,
    threshold: float = 0.92,
) -> NoveltyResult:
    """Check if text is novel compared to existing rooms.

    Embeds the text via ChromaDB's default embedding function and
    queries for the most similar existing room. If the cosine similarity
    is below the threshold, the text is considered novel.

    Args:
        store: Connected ChromaDBStore instance.
        text: The text to check for novelty.
        threshold: Maximum cosine similarity (1 - distance) allowed.
                   Default 0.92 per spec.

    Returns:
        NoveltyResult with is_novel flag, closest distance, and closest room ID.
    """
    if store.room_count() == 0:
        return NoveltyResult(is_novel=True, closest_distance=None, closest_room_id=None)

    results = store.query_similar(text, n=1)

    if not results:
        return NoveltyResult(is_novel=True, closest_distance=None, closest_room_id=None)

    closest = results[0]
    distance = closest.get("distance")

    if distance is None:
        return NoveltyResult(is_novel=True, closest_distance=None, closest_room_id=None)

    similarity = 1.0 - distance
    is_novel = similarity < threshold

    return NoveltyResult(
        is_novel=is_novel,
        closest_distance=distance,
        closest_room_id=closest.get("id"),
    )
