"""Tests for app.config — config loading, env var overrides, validation."""

import os
import textwrap
from pathlib import Path

import pytest
import yaml

from app.config import (
    BudgetConfig,
    CreativityConfig,
    Settings,
    StorageConfig,
    load_settings,
)


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """Create a temporary config.yaml with default values."""
    config = {
        "heartbeat_interval": 3600,
        "model": "openai/gpt-5.4",
        "budget": {"per_cycle": 2.0, "daily": 20.0, "monthly": 300.0},
        "creativity": {
            "temperature_range": [0.7, 1.0],
            "novelty_threshold": 0.92,
            "meta_reflection_every": 10,
            "wildcard_every": 5,
        },
        "storage": {
            "data_dir": "./data",
            "chromadb_dir": "./data/chromadb",
            "sqlite_path": "./data/thelife.db",
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(config))
    return path


@pytest.fixture
def empty_config(tmp_path: Path) -> Path:
    """Create an empty config.yaml."""
    path = tmp_path / "config.yaml"
    path.write_text("")
    return path


class TestLoadSettings:
    """Test config loading from YAML file."""

    def test_load_defaults_from_yaml(self, config_file: Path) -> None:
        settings = load_settings(config_path=config_file)
        assert settings.heartbeat_interval == 3600
        assert settings.model == "openai/gpt-5.4"

    def test_load_budget_from_yaml(self, config_file: Path) -> None:
        settings = load_settings(config_path=config_file)
        assert settings.budget.per_cycle == 2.0
        assert settings.budget.daily == 20.0
        assert settings.budget.monthly == 300.0

    def test_load_creativity_from_yaml(self, config_file: Path) -> None:
        settings = load_settings(config_path=config_file)
        assert settings.creativity.temperature_min == 0.7
        assert settings.creativity.temperature_max == 1.0
        assert settings.creativity.novelty_threshold == 0.92
        assert settings.creativity.meta_reflection_every == 10
        assert settings.creativity.wildcard_every == 5

    def test_load_storage_from_yaml(self, config_file: Path) -> None:
        settings = load_settings(config_path=config_file)
        assert settings.storage.data_dir == "./data"
        assert settings.storage.chromadb_dir == "./data/chromadb"
        assert settings.storage.sqlite_path == "./data/thelife.db"

    def test_load_with_missing_file(self, tmp_path: Path) -> None:
        """Missing config.yaml should use all defaults."""
        path = tmp_path / "nonexistent.yaml"
        settings = load_settings(config_path=path)
        assert settings.heartbeat_interval == 3600
        assert settings.model == "openai/gpt-5.4"

    def test_load_with_empty_file(self, empty_config: Path) -> None:
        """Empty config.yaml should use all defaults."""
        settings = load_settings(config_path=empty_config)
        assert settings.heartbeat_interval == 3600

    def test_load_partial_yaml(self, tmp_path: Path) -> None:
        """Partial config.yaml should merge with defaults."""
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump({"heartbeat_interval": 7200}))
        settings = load_settings(config_path=path)
        assert settings.heartbeat_interval == 7200
        assert settings.model == "openai/gpt-5.4"  # default


class TestEnvVarOverride:
    """Test that environment variables override config.yaml values."""

    def test_env_overrides_heartbeat(
        self, config_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("THELIFE_HEARTBEAT_INTERVAL", "1800")
        settings = load_settings(config_path=config_file)
        assert settings.heartbeat_interval == 1800

    def test_env_overrides_model(
        self, config_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("THELIFE_MODEL", "anthropic/claude-4")
        settings = load_settings(config_path=config_file)
        assert settings.model == "anthropic/claude-4"

    def test_api_keys_from_env(
        self, config_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("THELIFE_OPENROUTER_API_KEY", "sk-test-123")
        monkeypatch.setenv("THELIFE_REPLICATE_API_TOKEN", "r8_test456")
        monkeypatch.setenv("THELIFE_BRAVE_API_KEY", "BSA_test789")
        settings = load_settings(config_path=config_file)
        assert settings.openrouter_api_key == "sk-test-123"
        assert settings.replicate_api_token == "r8_test456"
        assert settings.brave_api_key == "BSA_test789"


class TestMissingApiKeys:
    """Test that missing API keys are properly detected."""

    def test_all_keys_missing(self, config_file: Path) -> None:
        settings = load_settings(config_path=config_file)
        missing = settings.validate_api_keys()
        assert "THELIFE_OPENROUTER_API_KEY" in missing
        assert "THELIFE_REPLICATE_API_TOKEN" in missing
        assert "THELIFE_BRAVE_API_KEY" in missing

    def test_some_keys_present(
        self, config_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("THELIFE_OPENROUTER_API_KEY", "sk-test")
        settings = load_settings(config_path=config_file)
        missing = settings.validate_api_keys()
        assert "THELIFE_OPENROUTER_API_KEY" not in missing
        assert "THELIFE_REPLICATE_API_TOKEN" in missing
        assert "THELIFE_BRAVE_API_KEY" in missing

    def test_all_keys_present(
        self, config_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("THELIFE_OPENROUTER_API_KEY", "sk-test")
        monkeypatch.setenv("THELIFE_REPLICATE_API_TOKEN", "r8_test")
        monkeypatch.setenv("THELIFE_BRAVE_API_KEY", "BSA_test")
        settings = load_settings(config_path=config_file)
        missing = settings.validate_api_keys()
        assert missing == []


class TestBudgetBoundsValidation:
    """Test budget config bounds are enforced."""

    def test_per_cycle_too_low(self) -> None:
        with pytest.raises(Exception):
            BudgetConfig(per_cycle=0.001)

    def test_per_cycle_too_high(self) -> None:
        with pytest.raises(Exception):
            BudgetConfig(per_cycle=200.0)

    def test_daily_too_low(self) -> None:
        with pytest.raises(Exception):
            BudgetConfig(daily=0.01)

    def test_daily_too_high(self) -> None:
        with pytest.raises(Exception):
            BudgetConfig(daily=5000.0)

    def test_monthly_too_low(self) -> None:
        with pytest.raises(Exception):
            BudgetConfig(monthly=0.5)

    def test_monthly_too_high(self) -> None:
        with pytest.raises(Exception):
            BudgetConfig(monthly=50000.0)

    def test_valid_budget(self) -> None:
        budget = BudgetConfig(per_cycle=1.5, daily=15.0, monthly=200.0)
        assert budget.per_cycle == 1.5
        assert budget.daily == 15.0
        assert budget.monthly == 200.0


class TestCreativityValidation:
    """Test creativity config bounds and temperature validation."""

    def test_temperature_max_below_min(self) -> None:
        with pytest.raises(Exception):
            CreativityConfig(temperature_min=0.9, temperature_max=0.5)

    def test_temperature_equal_valid(self) -> None:
        config = CreativityConfig(temperature_min=0.8, temperature_max=0.8)
        assert config.temperature_min == 0.8
        assert config.temperature_max == 0.8

    def test_novelty_threshold_out_of_range(self) -> None:
        with pytest.raises(Exception):
            CreativityConfig(novelty_threshold=1.5)

    def test_meta_reflection_too_low(self) -> None:
        with pytest.raises(Exception):
            CreativityConfig(meta_reflection_every=0)

    def test_wildcard_too_low(self) -> None:
        with pytest.raises(Exception):
            CreativityConfig(wildcard_every=0)


class TestHeartbeatBounds:
    """Test heartbeat_interval bounds validation."""

    def test_heartbeat_too_low(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump({"heartbeat_interval": 10}))
        with pytest.raises(Exception):
            load_settings(config_path=path)

    def test_heartbeat_too_high(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump({"heartbeat_interval": 100000}))
        with pytest.raises(Exception):
            load_settings(config_path=path)

    def test_heartbeat_valid_min(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump({"heartbeat_interval": 60}))
        settings = load_settings(config_path=path)
        assert settings.heartbeat_interval == 60

    def test_heartbeat_valid_max(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump({"heartbeat_interval": 86400}))
        settings = load_settings(config_path=path)
        assert settings.heartbeat_interval == 86400


class TestConfigYamlSecurity:
    """Test that config.yaml cannot inject API keys."""

    def test_yaml_cannot_set_api_keys(self, tmp_path: Path) -> None:
        """API keys in config.yaml should NOT be loaded (they come from env only)."""
        config = {
            "openrouter_api_key": "sk-should-not-load",
            "replicate_api_token": "r8_should-not-load",
            "brave_api_key": "BSA_should-not-load",
        }
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(config))
        settings = load_settings(config_path=path)
        # The load_settings function only reads specific keys from YAML,
        # so API keys from YAML are ignored
        assert settings.openrouter_api_key == ""
        assert settings.replicate_api_token == ""
        assert settings.brave_api_key == ""
