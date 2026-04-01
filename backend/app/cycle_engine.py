"""AI Cycle Engine — orchestrates the full room creation cycle.

Flow: gather_context → decision_phase → execute_tools → creation_phase
     → novelty_check → persist

Security: never logs full API keys, sanitizes user-influenced data in logs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings
from app.llm_client import LLMClient, LLMResponse
from app.memory.chromadb_store import ChromaDBStore
from app.memory.novelty import check_novelty
from app.prompts.creation import build_creation_prompt
from app.prompts.decision import TOOL_DEFINITIONS, build_decision_prompt
from app.prompts.system import get_system_prompt
from app.storage.sqlite_store import SQLiteStore
from app.tools import image_gen, music_gen, web_search

logger = logging.getLogger(__name__)


@dataclass
class CycleResult:
    """Result of a single AI cycle."""

    room_id: str = ""
    cycle_number: int = 0
    success: bool = False
    room_data: dict[str, Any] = field(default_factory=dict)
    decision_data: dict[str, Any] = field(default_factory=dict)
    search_results: list[dict[str, Any]] = field(default_factory=list)
    image_path: str | None = None
    music_path: str | None = None
    llm_tokens: int = 0
    llm_cost: float = 0.0
    image_cost: float = 0.0
    music_cost: float = 0.0
    search_cost: float = 0.0
    total_cost: float = 0.0
    duration_ms: int = 0
    error: str | None = None
    logs: list[str] = field(default_factory=list)


class CycleEngine:
    """Orchestrates the full AI cycle."""

    def __init__(
        self,
        settings: Settings,
        llm: LLMClient,
        chromadb: ChromaDBStore,
        sqlite: SQLiteStore,
        data_dir: Path,
    ) -> None:
        self._settings = settings
        self._llm = llm
        self._chromadb = chromadb
        self._sqlite = sqlite
        self._data_dir = data_dir

    async def run_cycle(self) -> CycleResult:
        """Execute one full AI cycle."""
        start = time.monotonic()
        result = CycleResult()
        result.room_id = str(uuid.uuid4())

        try:
            # Get cycle number
            result.cycle_number = await self._sqlite.count_rooms() + 1
            result.logs.append(f"[CYCLE] Starting cycle #{result.cycle_number}")

            # Budget check
            daily_cost = await self._sqlite.daily_cost(
                datetime.now(timezone.utc).strftime("%Y-%m-%d")
            )
            budget_remaining = self._settings.budget.daily - daily_cost
            if budget_remaining <= 0:
                result.error = "Daily budget exhausted"
                result.logs.append("[BUDGET] Daily budget exhausted, skipping cycle")
                return result

            # 1. Gather context
            result.logs.append("[CONTEXT] Gathering context from memory...")
            context = await self._gather_context(result.cycle_number)

            # 2. Decision phase
            result.logs.append("[DECISION] Running decision phase (LLM call #1)...")
            temperature = random.uniform(
                self._settings.creativity.temperature_min,
                self._settings.creativity.temperature_max,
            )
            decision_response = await self._decision_phase(context, budget_remaining, temperature)
            decision = decision_response.parsed_json or {}
            result.decision_data = decision
            result.llm_tokens += decision_response.usage.total_tokens
            result.logs.append(f"[DECISION] Intention: {decision.get('intention', '?')}")
            result.logs.append(f"[DECISION] Mood: {decision.get('mood', '?')}")
            result.logs.append(f"[DECISION] Tools: {decision.get('tools_to_use', [])}")

            # 3. Execute tools (parallel)
            result.logs.append("[TOOLS] Executing tools...")
            tool_results = await self._execute_tools(
                decision, result.room_id, budget_remaining
            )
            result.search_results = tool_results.get("search_results", [])
            result.image_path = tool_results.get("image_path")
            result.music_path = tool_results.get("music_path")
            result.search_cost = tool_results.get("search_cost", 0.0)
            result.image_cost = tool_results.get("image_cost", 0.0)
            result.music_cost = tool_results.get("music_cost", 0.0)

            if result.search_results:
                result.logs.append(f"[TOOLS] Web search: {len(result.search_results)} results")
            if result.image_path:
                result.logs.append(f"[TOOLS] Image generated: {result.image_path}")
            if result.music_path:
                result.logs.append(f"[TOOLS] Music generated: {result.music_path}")

            # 4. Creation phase
            result.logs.append("[CREATION] Running creation phase (LLM call #2)...")
            recent_ids = [r.get("id", "") for r in context["recent_rooms"]]
            creation_response = await self._creation_phase(
                decision, result.search_results, result.image_path,
                result.music_path, recent_ids, temperature,
            )
            room_data = creation_response.parsed_json or {}
            result.room_data = room_data
            result.llm_tokens += creation_response.usage.total_tokens
            result.logs.append(f"[CREATION] Title: {room_data.get('title', '?')}")
            result.logs.append(f"[CREATION] Type: {room_data.get('content_type', '?')}")

            # 5. Novelty check
            content = room_data.get("content", "")
            if content:
                result.logs.append("[NOVELTY] Checking novelty...")
                novelty = check_novelty(
                    self._chromadb, content,
                    threshold=self._settings.creativity.novelty_threshold,
                )
                if not novelty.is_novel:
                    result.logs.append("[NOVELTY] Too similar! Retrying with nudge...")
                    creation_response = await self._creation_phase(
                        decision, result.search_results, result.image_path,
                        result.music_path, recent_ids, min(temperature + 0.2, 2.0),
                        nudge="Your previous attempt was too similar to existing rooms. Be MORE original and explore a DIFFERENT angle.",
                    )
                    room_data = creation_response.parsed_json or room_data
                    result.room_data = room_data
                    result.llm_tokens += creation_response.usage.total_tokens

            # 6. Persist
            result.logs.append("[PERSIST] Saving room to storage...")
            await self._persist(result)
            result.success = True
            result.logs.append(f"[DONE] Cycle #{result.cycle_number} complete!")

            # Meta-reflection check
            if result.cycle_number % self._settings.creativity.meta_reflection_every == 0:
                result.logs.append("[META] Triggering meta-reflection...")
                await self._meta_reflection(result.cycle_number)

        except Exception as e:
            result.error = str(e)
            result.logs.append(f"[ERROR] Cycle failed: {e}")
            logger.exception("Cycle %s failed", result.cycle_number)

        result.duration_ms = int((time.monotonic() - start) * 1000)
        result.total_cost = result.llm_cost + result.image_cost + result.music_cost + result.search_cost
        result.logs.append(f"[STATS] Duration: {result.duration_ms}ms, Cost: ${result.total_cost:.4f}, Tokens: {result.llm_tokens}")
        return result

    def _get_latest_arc(self) -> dict[str, Any] | None:
        """Get latest journey arc — wrapper for scheduler's ChromaDBStore API."""
        arcs = self._chromadb.query_arcs("latest journey", n=1)
        return arcs[0] if arcs else None

    async def _gather_context(self, cycle_number: int) -> dict[str, Any]:
        """Gather context from ChromaDB and SQLite."""
        recent_rooms = self._chromadb.query_recent(n=5)
        arc = self._get_latest_arc()

        # Build anti-repetition list from recent rooms
        anti_rep: list[str] = []
        for r in recent_rooms[:10]:
            meta = r.get("metadata", {})
            if meta.get("mood"):
                anti_rep.append(str(meta["mood"]))
            tags = meta.get("tags", "")
            if isinstance(tags, str) and tags:
                anti_rep.extend(tags.split(", ")[:2])

        # Get similar rooms based on latest room's content (if exists)
        similar: list[dict[str, Any]] = []
        if recent_rooms:
            latest_doc = recent_rooms[0].get("document", "")
            if latest_doc:
                similar = self._chromadb.query_similar(latest_doc, n=3)

        return {
            "recent_rooms": recent_rooms,
            "similar_rooms": similar,
            "arc_summary": arc.get("document") if arc else None,
            "anti_repetition": anti_rep[:15],
            "cycle_number": cycle_number,
            "total_rooms": self._chromadb.room_count(),
        }

    async def _decision_phase(
        self,
        context: dict[str, Any],
        budget_remaining: float,
        temperature: float,
    ) -> LLMResponse:
        """LLM Call #1 — decide what to explore."""
        user_prompt = build_decision_prompt(
            recent_rooms=context["recent_rooms"],
            similar_rooms=context["similar_rooms"],
            arc_summary=context["arc_summary"],
            anti_repetition=context["anti_repetition"],
            budget_remaining=budget_remaining,
            cycle_number=context["cycle_number"],
            total_rooms=context["total_rooms"],
        )

        return await self._llm.decision_call(
            messages=[
                {"role": "system", "content": get_system_prompt()},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )

    async def _execute_tools(
        self,
        decision: dict[str, Any],
        room_id: str,
        budget_remaining: float,
    ) -> dict[str, Any]:
        """Execute tools in parallel based on decision."""
        tools_to_use = decision.get("tools_to_use", [])
        results: dict[str, Any] = {
            "search_results": [],
            "image_path": None,
            "music_path": None,
            "search_cost": 0.0,
            "image_cost": 0.0,
            "music_cost": 0.0,
        }

        tasks: list[asyncio.Task] = []
        task_names: list[str] = []

        # Web search
        if "web_search" in tools_to_use:
            queries = decision.get("search_queries", [])
            if queries and self._settings.brave_api_key:
                async def do_search() -> list[dict[str, Any]]:
                    all_results: list[dict[str, Any]] = []
                    for q in queries[:3]:  # max 3 queries
                        try:
                            sr = await web_search.search(q, self._settings.brave_api_key)
                            for r in sr:
                                all_results.append({"title": r.title, "url": r.url, "snippet": r.snippet})
                        except Exception:
                            logger.exception("Search failed for query: %s", q[:50])
                    return all_results

                tasks.append(asyncio.create_task(do_search()))
                task_names.append("search")

        # Image generation
        if "generate_image" in tools_to_use and budget_remaining > 0.5:
            img_prompt = decision.get("image_prompt")
            if img_prompt and self._settings.replicate_api_token:
                room_dir = self._data_dir / "rooms" / room_id

                async def do_image() -> str | None:
                    try:
                        path = await image_gen.generate_image(img_prompt, room_dir)
                        return str(path) if path else None
                    except Exception:
                        logger.exception("Image generation failed")
                        return None

                tasks.append(asyncio.create_task(do_image()))
                task_names.append("image")

        # Music generation
        if "generate_music" in tools_to_use and budget_remaining > 1.0:
            music_prompt = decision.get("music_prompt")
            if music_prompt and self._settings.replicate_api_token:
                room_dir = self._data_dir / "rooms" / room_id

                async def do_music() -> str | None:
                    try:
                        path = await music_gen.generate_music(music_prompt, room_dir)
                        return str(path) if path else None
                    except Exception:
                        logger.exception("Music generation failed")
                        return None

                tasks.append(asyncio.create_task(do_music()))
                task_names.append("music")

        # Run all in parallel
        if tasks:
            completed = await asyncio.gather(*tasks, return_exceptions=True)
            for name, result in zip(task_names, completed):
                if isinstance(result, Exception):
                    logger.error("Tool %s failed: %s", name, result)
                    continue
                if name == "search":
                    results["search_results"] = result or []
                    results["search_cost"] = len(result or []) * 0.003
                elif name == "image":
                    results["image_path"] = result
                    results["image_cost"] = 0.04 if result else 0.0
                elif name == "music":
                    results["music_path"] = result
                    results["music_cost"] = 0.10 if result else 0.0

        return results

    async def _creation_phase(
        self,
        decision: dict[str, Any],
        search_results: list[dict[str, Any]],
        image_path: str | None,
        music_path: str | None,
        recent_ids: list[str],
        temperature: float,
        nudge: str | None = None,
    ) -> LLMResponse:
        """LLM Call #2 — create the room content."""
        user_prompt = build_creation_prompt(
            decision=decision,
            search_results=search_results,
            image_path=image_path,
            music_path=music_path,
            recent_room_ids=recent_ids,
        )

        if nudge:
            user_prompt = f"⚠ {nudge}\n\n{user_prompt}"

        return await self._llm.creation_call(
            messages=[
                {"role": "system", "content": get_system_prompt()},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )

    async def _persist(self, result: CycleResult) -> None:
        """Save room to ChromaDB + SQLite."""
        room = result.room_data
        now = datetime.now(timezone.utc).isoformat()

        # Full room record for SQLite
        full_record = {
            "id": result.room_id,
            "cycle_number": result.cycle_number,
            "created_at": now,
            "title": room.get("title", "Untitled"),
            "content": room.get("content", ""),
            "content_type": room.get("content_type", "reflection"),
            "mood": result.decision_data.get("mood", ""),
            "tags": room.get("tags", []),
            "image_url": result.image_path,
            "image_prompt": result.decision_data.get("image_prompt"),
            "music_url": result.music_path,
            "music_prompt": result.decision_data.get("music_prompt"),
            "intention": result.decision_data.get("intention", ""),
            "reasoning": result.decision_data.get("reasoning", ""),
            "search_queries": result.decision_data.get("search_queries", []),
            "search_results": result.search_results,
            "next_hint": room.get("next_direction_hint", ""),
            "connections": room.get("connections", []),
            "model": self._settings.model,
            "llm_tokens": result.llm_tokens,
            "llm_cost": result.llm_cost,
            "image_cost": result.image_cost,
            "music_cost": result.music_cost,
            "search_cost": result.search_cost,
            "total_cost": result.total_cost,
            "duration_ms": result.duration_ms,
        }

        # SQLite
        await self._sqlite.insert_room(result.room_id, result.cycle_number, now, full_record)

        # Stats
        await self._sqlite.insert_stats(
            stat_id=str(uuid.uuid4()),
            cycle_number=result.cycle_number,
            created_at=now,
            model=self._settings.model,
            llm_tokens=result.llm_tokens,
            llm_cost=result.llm_cost,
            image_cost=result.image_cost,
            music_cost=result.music_cost,
            search_cost=result.search_cost,
            total_cost=result.total_cost,
            duration_ms=result.duration_ms,
        )

        # ChromaDB
        tags = room.get("tags", [])
        tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
        self._chromadb.add_room(
            room_id=result.room_id,
            content=room.get("content", ""),
            metadata={
                "title": room.get("title", ""),
                "cycle_number": result.cycle_number,
                "content_type": room.get("content_type", ""),
                "mood": result.decision_data.get("mood", ""),
                "tags": tags_str,
            },
        )

        # Cache search results
        for i, sr in enumerate(result.search_results):
            self._chromadb.add_search_result(
                search_id=f"{result.room_id}-search-{i}",
                query=sr.get("title", ""),
                metadata={"query": sr.get("title", ""), "source_url": sr.get("url", "")},
            )

    async def _meta_reflection(self, cycle_number: int) -> None:
        """Run meta-reflection — AI reviews its journey every N cycles."""
        try:
            recent = self._chromadb.query_recent(n=10)
            if not recent:
                return

            summaries = []
            for r in recent:
                meta = r.get("metadata", {})
                summaries.append(f"- {meta.get('title', '?')} [{meta.get('content_type', '?')}] mood={meta.get('mood', '?')}")

            prompt = f"""Review your last 10 rooms and reflect on your journey:

{chr(10).join(summaries)}

Output JSON:
{{
    "arc_summary": "A 2-3 sentence summary of your journey arc — themes, growth, patterns",
    "blind_spots": "Topics or styles you haven't explored yet",
    "next_arc_direction": "Where you want to take your journey next"
}}"""

            response = await self._llm.creation_call(
                messages=[
                    {"role": "system", "content": get_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )

            if response.parsed_json:
                arc_data = response.parsed_json
                self._chromadb.add_arc(
                    arc_id=f"arc-{cycle_number}",
                    summary=arc_data.get("arc_summary", ""),
                    metadata={
                        "end_cycle": cycle_number,
                        "start_cycle": max(1, cycle_number - 10),
                        "themes": arc_data.get("next_arc_direction", ""),
                    },
                )
                logger.info("Meta-reflection saved for cycle %d", cycle_number)
        except Exception:
            logger.exception("Meta-reflection failed at cycle %d", cycle_number)
