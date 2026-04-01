"""ChromaDB PersistentClient wrapper for vector storage.

Three collections:
- rooms: room content embeddings with metadata
- journey_arcs: arc summaries for meta-reflection
- search_cache: cached search query embeddings
"""

from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection


class ChromaDBStore:
    """Wrapper around ChromaDB PersistentClient with three collections."""

    COLLECTION_ROOMS = "rooms"
    COLLECTION_ARCS = "journey_arcs"
    COLLECTION_SEARCH = "search_cache"

    def __init__(self, persist_dir: str) -> None:
        self._persist_dir = persist_dir
        self._client: chromadb.ClientAPI | None = None
        self._rooms: Collection | None = None
        self._arcs: Collection | None = None
        self._search: Collection | None = None

    def connect(self) -> None:
        """Initialize PersistentClient and get or create collections."""
        self._client = chromadb.PersistentClient(path=self._persist_dir)
        self._rooms = self._client.get_or_create_collection(
            name=self.COLLECTION_ROOMS,
            metadata={"hnsw:space": "cosine"},
        )
        self._arcs = self._client.get_or_create_collection(
            name=self.COLLECTION_ARCS,
            metadata={"hnsw:space": "cosine"},
        )
        self._search = self._client.get_or_create_collection(
            name=self.COLLECTION_SEARCH,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def rooms(self) -> Collection:
        if self._rooms is None:
            raise RuntimeError("ChromaDBStore not connected. Call connect() first.")
        return self._rooms

    @property
    def arcs(self) -> Collection:
        if self._arcs is None:
            raise RuntimeError("ChromaDBStore not connected. Call connect() first.")
        return self._arcs

    @property
    def search(self) -> Collection:
        if self._search is None:
            raise RuntimeError("ChromaDBStore not connected. Call connect() first.")
        return self._search

    # ── Rooms ────────────────────────────────────────────────────────────

    def add_room(
        self,
        room_id: str,
        content: str,
        metadata: dict[str, Any],
    ) -> None:
        """Add a room embedding with metadata.

        Args:
            room_id: UUID string for the room.
            content: Room text content to embed.
            metadata: Must include keys like tags, mood, content_type, cycle_number.
                      ChromaDB metadata values must be str, int, float, or bool.
        """
        safe_meta = _sanitize_metadata(metadata)
        self.rooms.upsert(
            ids=[room_id],
            documents=[content],
            metadatas=[safe_meta],
        )

    def query_recent(self, n: int = 5) -> list[dict[str, Any]]:
        """Get the N most recent rooms by cycle_number (descending).

        Uses a dummy query and relies on ChromaDB returning all results,
        then sorts by cycle_number. For small collections this is efficient.
        """
        count = self.rooms.count()
        if count == 0:
            return []
        fetch_n = min(n, count)
        results = self.rooms.get(
            limit=fetch_n,
            include=["documents", "metadatas"],
        )
        items = _unpack_get_results(results)
        items.sort(key=lambda x: x.get("metadata", {}).get("cycle_number", 0), reverse=True)
        return items[:n]

    def query_similar(self, text: str, n: int = 3) -> list[dict[str, Any]]:
        """Find N rooms most similar to the given text.

        Args:
            text: Query text to embed and compare against.
            n: Number of results to return.

        Returns:
            List of dicts with id, document, metadata, distance.
        """
        count = self.rooms.count()
        if count == 0:
            return []
        fetch_n = min(n, count)
        results = self.rooms.query(
            query_texts=[text],
            n_results=fetch_n,
            include=["documents", "metadatas", "distances"],
        )
        return _unpack_query_results(results)

    def get_room(self, room_id: str) -> dict[str, Any] | None:
        """Get a single room by ID."""
        results = self.rooms.get(
            ids=[room_id],
            include=["documents", "metadatas"],
        )
        items = _unpack_get_results(results)
        return items[0] if items else None

    # ── Journey Arcs ─────────────────────────────────────────────────────

    def add_arc(
        self,
        arc_id: str,
        summary: str,
        metadata: dict[str, Any],
    ) -> None:
        """Add a journey arc embedding.

        Args:
            arc_id: Unique ID for the arc.
            summary: Arc summary text to embed.
            metadata: Should include start_cycle, end_cycle, themes.
        """
        safe_meta = _sanitize_metadata(metadata)
        self.arcs.upsert(
            ids=[arc_id],
            documents=[summary],
            metadatas=[safe_meta],
        )

    def query_arcs(self, text: str, n: int = 3) -> list[dict[str, Any]]:
        """Find arcs similar to the given text."""
        count = self.arcs.count()
        if count == 0:
            return []
        fetch_n = min(n, count)
        results = self.arcs.query(
            query_texts=[text],
            n_results=fetch_n,
            include=["documents", "metadatas", "distances"],
        )
        return _unpack_query_results(results)

    # ── Search Cache ─────────────────────────────────────────────────────

    def add_search_result(
        self,
        search_id: str,
        query: str,
        metadata: dict[str, Any],
    ) -> None:
        """Cache a search query embedding.

        Args:
            search_id: Unique ID for this search entry.
            query: The search query text to embed.
            metadata: Should include query, source_url, etc.
        """
        safe_meta = _sanitize_metadata(metadata)
        self.search.upsert(
            ids=[search_id],
            documents=[query],
            metadatas=[safe_meta],
        )

    def query_search_cache(self, query: str, n: int = 3) -> list[dict[str, Any]]:
        """Find cached searches similar to the given query."""
        count = self.search.count()
        if count == 0:
            return []
        fetch_n = min(n, count)
        results = self.search.query(
            query_texts=[query],
            n_results=fetch_n,
            include=["documents", "metadatas", "distances"],
        )
        return _unpack_query_results(results)

    # ── Utilities ────────────────────────────────────────────────────────

    def room_count(self) -> int:
        """Return the number of rooms in the collection."""
        return self.rooms.count()

    def arc_count(self) -> int:
        """Return the number of arcs in the collection."""
        return self.arcs.count()

    def search_count(self) -> int:
        """Return the number of cached searches."""
        return self.search.count()


def _sanitize_metadata(meta: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """Ensure all metadata values are ChromaDB-compatible types.

    ChromaDB only supports str, int, float, bool as metadata values.
    Lists are joined as comma-separated strings; other types are cast to str.
    """
    sanitized: dict[str, str | int | float | bool] = {}
    for key, value in meta.items():
        if isinstance(value, (str, int, float, bool)):
            sanitized[key] = value
        elif isinstance(value, list):
            sanitized[key] = ",".join(str(v) for v in value)
        elif value is None:
            continue
        else:
            sanitized[key] = str(value)
    return sanitized


def _unpack_get_results(results: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert ChromaDB get() results into a list of dicts."""
    items: list[dict[str, Any]] = []
    ids = results.get("ids") or []
    documents = results.get("documents") or []
    metadatas = results.get("metadatas") or []
    for i, rid in enumerate(ids):
        items.append({
            "id": rid,
            "document": documents[i] if i < len(documents) else None,
            "metadata": metadatas[i] if i < len(metadatas) else {},
        })
    return items


def _unpack_query_results(results: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert ChromaDB query() results into a flat list of dicts."""
    items: list[dict[str, Any]] = []
    ids_list = results.get("ids") or [[]]
    docs_list = results.get("documents") or [[]]
    metas_list = results.get("metadatas") or [[]]
    dists_list = results.get("distances") or [[]]

    # query() returns nested lists (one per query text); we only use one query.
    ids = ids_list[0] if ids_list else []
    documents = docs_list[0] if docs_list else []
    metadatas = metas_list[0] if metas_list else []
    distances = dists_list[0] if dists_list else []

    for i, rid in enumerate(ids):
        items.append({
            "id": rid,
            "document": documents[i] if i < len(documents) else None,
            "metadata": metadatas[i] if i < len(metadatas) else {},
            "distance": distances[i] if i < len(distances) else None,
        })
    return items
