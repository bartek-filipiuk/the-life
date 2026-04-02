"""Dynamic tool registry — tools configured via admin, stored in SQLite.

Each tool has: id, name, category, api_type, provider, model, enabled, daily_limit, cost_estimate, config.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)

REGISTRY_KEY = "tool_registry"
USAGE_KEY_PREFIX = "tool_usage_"


@dataclass
class ToolConfig:
    """Configuration for a single tool."""

    id: str
    name: str
    category: str  # search, image, video, music, custom
    api_type: str  # openrouter, replicate, custom_http, builtin
    provider: str  # e.g. "replicate", "openrouter", "brave", "tavily"
    model: str  # e.g. "black-forest-labs/flux-schnell"
    enabled: bool = True
    daily_limit: int = 0  # 0 = unlimited
    cost_estimate: float = 0.0
    config: dict[str, Any] = field(default_factory=dict)  # extra config (endpoint_url, etc.)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "api_type": self.api_type,
            "provider": self.provider,
            "model": self.model,
            "enabled": self.enabled,
            "daily_limit": self.daily_limit,
            "cost_estimate": self.cost_estimate,
            "config": self.config,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolConfig:
        return cls(
            id=data["id"],
            name=data["name"],
            category=data["category"],
            api_type=data.get("api_type", "builtin"),
            provider=data.get("provider", ""),
            model=data.get("model", ""),
            enabled=data.get("enabled", True),
            daily_limit=data.get("daily_limit", 0),
            cost_estimate=data.get("cost_estimate", 0.0),
            config=data.get("config", {}),
        )


# Default tools that ship with the system
DEFAULT_TOOLS: list[dict[str, Any]] = [
    {
        "id": "web_search",
        "name": "Web Search",
        "category": "search",
        "api_type": "builtin",
        "provider": "brave",
        "model": "",
        "enabled": True,
        "daily_limit": 50,
        "cost_estimate": 0.005,
    },
    {
        "id": "generate_image",
        "name": "Image Generation",
        "category": "image",
        "api_type": "replicate",
        "provider": "replicate",
        "model": "black-forest-labs/flux-schnell",
        "enabled": True,
        "daily_limit": 20,
        "cost_estimate": 0.04,
    },
    {
        "id": "generate_music",
        "name": "Music Generation",
        "category": "music",
        "api_type": "replicate",
        "provider": "replicate",
        "model": "meta/musicgen:stereo-melody-large",
        "enabled": True,
        "daily_limit": 10,
        "cost_estimate": 0.10,
    },
    {
        "id": "generate_video",
        "name": "Video Generation",
        "category": "video",
        "api_type": "replicate",
        "provider": "replicate",
        "model": "",
        "enabled": False,
        "daily_limit": 5,
        "cost_estimate": 0.50,
    },
]


class ToolRegistry:
    """Manages tool configurations, persisted in SQLite config table."""

    def __init__(self, sqlite: SQLiteStore) -> None:
        self._sqlite = sqlite
        self._tools: dict[str, ToolConfig] = {}
        self._daily_usage: dict[str, int] = {}
        self._usage_date: str = ""

    async def load(self) -> None:
        """Load tools from SQLite, or initialize with defaults."""
        raw = await self._sqlite.get_config(REGISTRY_KEY)
        if raw:
            data = json.loads(raw)
            self._tools = {t["id"]: ToolConfig.from_dict(t) for t in data}
        else:
            self._tools = {t["id"]: ToolConfig.from_dict(t) for t in DEFAULT_TOOLS}
            await self._save()

        await self._load_daily_usage()

    async def _save(self) -> None:
        """Persist tools to SQLite."""
        data = [t.to_dict() for t in self._tools.values()]
        await self._sqlite.set_config(REGISTRY_KEY, json.dumps(data))

    async def _load_daily_usage(self) -> None:
        """Load today's usage counts."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._usage_date != today:
            self._daily_usage = {}
            self._usage_date = today

        raw = await self._sqlite.get_config(f"{USAGE_KEY_PREFIX}{today}")
        if raw:
            self._daily_usage = json.loads(raw)

    async def _save_usage(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await self._sqlite.set_config(
            f"{USAGE_KEY_PREFIX}{today}", json.dumps(self._daily_usage)
        )

    def list_tools(self) -> list[ToolConfig]:
        """Return all registered tools."""
        return list(self._tools.values())

    def get_tool(self, tool_id: str) -> ToolConfig | None:
        return self._tools.get(tool_id)

    def get_enabled_tools(self) -> list[ToolConfig]:
        """Return tools that are enabled and within daily limits."""
        result = []
        for tool in self._tools.values():
            if not tool.enabled:
                continue
            if tool.daily_limit > 0:
                used = self._daily_usage.get(tool.id, 0)
                if used >= tool.daily_limit:
                    continue
            result.append(tool)
        return result

    def is_available(self, tool_id: str) -> bool:
        """Check if a tool is enabled and within its daily limit."""
        tool = self._tools.get(tool_id)
        if not tool or not tool.enabled:
            return False
        if tool.daily_limit > 0:
            used = self._daily_usage.get(tool_id, 0)
            if used >= tool.daily_limit:
                return False
        return True

    async def record_usage(self, tool_id: str) -> None:
        """Record one usage of a tool for today."""
        await self._load_daily_usage()
        self._daily_usage[tool_id] = self._daily_usage.get(tool_id, 0) + 1
        await self._save_usage()

    def get_usage(self, tool_id: str) -> int:
        return self._daily_usage.get(tool_id, 0)

    async def update_tool(self, tool_id: str, updates: dict[str, Any]) -> ToolConfig | None:
        """Update a tool's configuration."""
        tool = self._tools.get(tool_id)
        if not tool:
            return None
        for key, value in updates.items():
            if value is not None and hasattr(tool, key):
                setattr(tool, key, value)
        await self._save()
        return tool

    async def add_tool(self, data: dict[str, Any]) -> ToolConfig:
        """Add a new custom tool."""
        tool = ToolConfig.from_dict(data)
        self._tools[tool.id] = tool
        await self._save()
        return tool

    async def remove_tool(self, tool_id: str) -> bool:
        """Remove a tool. Returns True if found."""
        if tool_id in self._tools:
            del self._tools[tool_id]
            await self._save()
            return True
        return False

    def build_tool_definitions(self) -> list[dict[str, Any]]:
        """Generate OpenAI-compatible tool definitions for enabled tools."""
        definitions = []
        for tool in self.get_enabled_tools():
            if tool.category == "search":
                definitions.append({
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "description": f"Search the internet using {tool.provider}.",
                        "parameters": {
                            "type": "object",
                            "properties": {"query": {"type": "string", "description": "The search query"}},
                            "required": ["query"],
                        },
                    },
                })
            elif tool.category == "image":
                definitions.append({
                    "type": "function",
                    "function": {
                        "name": "generate_image",
                        "description": f"Create a visual artwork using {tool.model or 'image model'}.",
                        "parameters": {
                            "type": "object",
                            "properties": {"prompt": {"type": "string", "description": "Detailed image description"}},
                            "required": ["prompt"],
                        },
                    },
                })
            elif tool.category == "video":
                definitions.append({
                    "type": "function",
                    "function": {
                        "name": "generate_video",
                        "description": f"Generate a short video clip using {tool.model or 'video model'}.",
                        "parameters": {
                            "type": "object",
                            "properties": {"prompt": {"type": "string", "description": "Video scene description"}},
                            "required": ["prompt"],
                        },
                    },
                })
            elif tool.category == "music":
                definitions.append({
                    "type": "function",
                    "function": {
                        "name": "generate_music",
                        "description": f"Compose music using {tool.model or 'music model'}.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "prompt": {"type": "string", "description": "Music description"},
                                "duration": {"type": "integer", "description": "Duration in seconds (1-30)", "default": 8},
                            },
                            "required": ["prompt"],
                        },
                    },
                })
            elif tool.category == "custom":
                definitions.append({
                    "type": "function",
                    "function": {
                        "name": tool.id,
                        "description": tool.name,
                        "parameters": {
                            "type": "object",
                            "properties": {"input": {"type": "string", "description": "Input for the custom tool"}},
                            "required": ["input"],
                        },
                    },
                })
        return definitions

    def build_tool_names_for_prompt(self) -> list[str]:
        """Return tool names for the decision prompt."""
        names = []
        for tool in self.get_enabled_tools():
            if tool.category == "search":
                names.append("web_search")
            elif tool.category == "image":
                names.append("generate_image")
            elif tool.category == "video":
                names.append("generate_video")
            elif tool.category == "music":
                names.append("generate_music")
            else:
                names.append(tool.id)
        return names
