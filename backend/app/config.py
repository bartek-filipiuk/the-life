"""Application configuration loaded from config.yaml + environment variables.

Security: API keys come from env vars ONLY, never from config.yaml.
"""

import os
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BudgetConfig(BaseModel):
    per_cycle: Annotated[float, Field(ge=0.01, le=100.0)] = 2.0
    daily: Annotated[float, Field(ge=0.1, le=1000.0)] = 20.0
    monthly: Annotated[float, Field(ge=1.0, le=10000.0)] = 300.0


class CreativityConfig(BaseModel):
    temperature_min: Annotated[float, Field(ge=0.0, le=2.0)] = 0.7
    temperature_max: Annotated[float, Field(ge=0.0, le=2.0)] = 1.0
    novelty_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.92
    meta_reflection_every: Annotated[int, Field(ge=1, le=1000)] = 10
    wildcard_every: Annotated[int, Field(ge=1, le=1000)] = 5

    @field_validator("temperature_max")
    @classmethod
    def max_gte_min(cls, v: float, info: object) -> float:
        data = info.data if hasattr(info, "data") else {}
        if "temperature_min" in data and v < data["temperature_min"]:
            raise ValueError("temperature_max must be >= temperature_min")
        return v


class StorageConfig(BaseModel):
    data_dir: str = "./data"
    chromadb_dir: str = "./data/chromadb"
    sqlite_path: str = "./data/thelife.db"


class Settings(BaseSettings):
    """Main application settings.

    API keys are loaded from environment variables only.
    Other settings can come from config.yaml or env vars.
    """

    model_config = SettingsConfigDict(
        env_prefix="THELIFE_",
        env_nested_delimiter="__",
    )

    # API keys — env vars only, no defaults
    openrouter_api_key: str = ""
    replicate_api_token: str = ""
    brave_api_key: str = ""
    tavily_api_key: str = ""

    # Search provider: "brave" or "tavily"
    search_provider: str = "brave"

    # Runtime config
    heartbeat_interval: Annotated[int, Field(ge=60, le=86400)] = 3600
    model: str = "openai/gpt-5.4"

    # Nested config
    budget: BudgetConfig = BudgetConfig()
    creativity: CreativityConfig = CreativityConfig()
    storage: StorageConfig = StorageConfig()

    # Frontend CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:4321"]

    def validate_api_keys(self) -> list[str]:
        """Return list of missing API keys (empty list = all present)."""
        missing = []
        if not self.openrouter_api_key:
            missing.append("THELIFE_OPENROUTER_API_KEY")
        if not self.replicate_api_token:
            missing.append("THELIFE_REPLICATE_API_TOKEN")
        # Check search provider key
        if self.search_provider == "brave" and not self.brave_api_key:
            missing.append("THELIFE_BRAVE_API_KEY")
        if self.search_provider == "tavily" and not self.tavily_api_key:
            missing.append("THELIFE_TAVILY_API_KEY")
        return missing

    def get_search_api_key(self) -> str:
        """Return the API key for the configured search provider."""
        if self.search_provider == "tavily":
            return self.tavily_api_key
        return self.brave_api_key


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from config.yaml (if exists) merged with env vars.

    Env vars always take precedence over config.yaml values.
    API keys MUST come from env vars.
    """
    yaml_overrides: dict = {}

    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"

    if config_path.exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}

        env_prefix = "THELIFE_"

        # Flatten nested config for pydantic-settings.
        # Only use YAML value when the corresponding env var is NOT set,
        # so that env vars always take precedence.
        if "heartbeat_interval" in raw and env_prefix + "HEARTBEAT_INTERVAL" not in os.environ:
            yaml_overrides["heartbeat_interval"] = raw["heartbeat_interval"]
        if "model" in raw and env_prefix + "MODEL" not in os.environ:
            yaml_overrides["model"] = raw["model"]
        if "budget" in raw:
            yaml_overrides["budget"] = BudgetConfig(**raw["budget"])
        if "creativity" in raw:
            creativity_data = raw["creativity"]
            # Handle temperature_range → temperature_min/max conversion
            if "temperature_range" in creativity_data:
                tr = creativity_data.pop("temperature_range")
                creativity_data["temperature_min"] = tr[0]
                creativity_data["temperature_max"] = tr[1]
            yaml_overrides["creativity"] = CreativityConfig(**creativity_data)
        if "storage" in raw:
            yaml_overrides["storage"] = StorageConfig(**raw["storage"])
        if "cors_origins" in raw:
            yaml_overrides["cors_origins"] = raw["cors_origins"]

    return Settings(**yaml_overrides)
