"""Comment moderation with configurable guardrails.

Rule-based filter (sync) for quick rejection.
AI self-moderates with guardrails stored in SQLite config.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)

MODERATION_CONFIG_KEY = "moderation_config"


@dataclass
class ModerationConfig:
    """Configurable guardrails for comment moderation."""

    max_length: int = 1000
    rate_limit_per_hour: int = 5
    banned_words: list[str] = field(default_factory=list)
    require_name: bool = True
    auto_approve: bool = True  # If True, pass rule-based → approve. If False → pending.

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_length": self.max_length,
            "rate_limit_per_hour": self.rate_limit_per_hour,
            "banned_words": self.banned_words,
            "require_name": self.require_name,
            "auto_approve": self.auto_approve,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModerationConfig:
        return cls(
            max_length=data.get("max_length", 1000),
            rate_limit_per_hour=data.get("rate_limit_per_hour", 5),
            banned_words=data.get("banned_words", []),
            require_name=data.get("require_name", True),
            auto_approve=data.get("auto_approve", True),
        )


@dataclass
class ModerationResult:
    approved: bool
    reason: str = ""


class Moderator:
    """Moderates comments based on configurable rules."""

    def __init__(self, sqlite: SQLiteStore) -> None:
        self._sqlite = sqlite
        self._config = ModerationConfig()

    async def load_config(self) -> None:
        raw = await self._sqlite.get_config(MODERATION_CONFIG_KEY)
        if raw:
            self._config = ModerationConfig.from_dict(json.loads(raw))

    async def save_config(self, config: ModerationConfig) -> None:
        self._config = config
        await self._sqlite.set_config(MODERATION_CONFIG_KEY, json.dumps(config.to_dict()))

    @property
    def config(self) -> ModerationConfig:
        return self._config

    async def check(
        self, content: str, author_name: str, ip_hash: str
    ) -> ModerationResult:
        """Run moderation checks. Returns approved=True if passes all rules."""

        # Name required
        if self._config.require_name and not author_name.strip():
            return ModerationResult(approved=False, reason="Name is required")

        # Content length
        if not content.strip():
            return ModerationResult(approved=False, reason="Comment cannot be empty")

        if len(content) > self._config.max_length:
            return ModerationResult(
                approved=False,
                reason=f"Comment exceeds {self._config.max_length} characters",
            )

        # Banned words
        content_lower = content.lower()
        for word in self._config.banned_words:
            if word.lower() in content_lower:
                return ModerationResult(approved=False, reason="Contains prohibited content")

        # Rate limiting by IP hash
        recent_count = await self._sqlite.count_recent_comments(ip_hash)
        if recent_count >= self._config.rate_limit_per_hour:
            return ModerationResult(
                approved=False,
                reason=f"Rate limit: max {self._config.rate_limit_per_hour} comments per hour",
            )

        # Passed all checks
        status = "approved" if self._config.auto_approve else "pending"
        return ModerationResult(approved=True, reason=status)


def hash_ip(ip: str) -> str:
    """Hash an IP address for privacy-preserving rate limiting."""
    return hashlib.sha256(ip.encode()).hexdigest()[:16]
