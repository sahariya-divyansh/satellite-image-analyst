"""Tests for application settings and configuration."""

from satellite_analyst.config import Settings, get_settings


def test_default_settings() -> None:
    settings = get_settings()
    assert settings.app_env in ["development", "testing", "production"]
    assert settings.log_level in ["DEBUG", "INFO", "WARNING", "ERROR"]
    assert settings.stac_provider in ["planetary_computer", "earth_search"]
    assert settings.default_llm_provider in ["rule_based", "gemini", "openai", "ollama"]


def test_custom_settings_override() -> None:
    custom = Settings(
        app_env="testing",
        log_level="DEBUG",
        default_llm_provider="ollama",
        max_cache_size_gb=20,
    )
    assert custom.app_env == "testing"
    assert custom.log_level == "DEBUG"
    assert custom.default_llm_provider == "ollama"
    assert custom.max_cache_size_gb == 20
