"""Application and pipeline configuration module."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for satellite-analyst."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application settings
    app_env: Literal["development", "production", "testing"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    debug: bool = False

    # Cache and data storage
    cache_dir: Path = Field(default=Path("./data/cache"))
    max_cache_size_gb: int = 10

    # STAC Provider
    stac_provider: Literal["planetary_computer", "earth_search"] = "planetary_computer"
    pc_sdk_subscription_key: str | None = None

    # LLM Providers
    default_llm_provider: Literal["rule_based", "gemini", "openai", "ollama"] = "rule_based"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Geocoding & Area Limits
    geocoding_user_agent: str = (
        "satellite-image-analyst/0.1.0 (contact: research@satellite-analyst.local)"
    )
    max_aoi_area_km2: float = 2500.0

    # STAC Query Limits
    stac_max_cloud_cover: float = 40.0

    # Feature flags
    enable_experimental_clip_sam: bool = False


# Global cached settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Retrieve or initialize application settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
