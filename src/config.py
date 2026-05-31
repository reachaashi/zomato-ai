"""Application configuration (architecture §10)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings loaded from `.env` and process env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    hf_dataset_name: str = Field(
        default="ManikaSaini/zomato-restaurant-recommendation",
        description="Hugging Face dataset id",
    )
    llm_provider: str = Field(default="groq", description="LLM provider (Groq for Phase P2)")
    llm_api_key: str | None = Field(default=None, description="Groq API key (never commit)")
    llm_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Groq model id for chat completions",
    )
    llm_timeout: float = Field(
        default=15.0,
        ge=1.0,
        description="Timeout for LLM API requests in seconds",
    )
    cache_ttl_seconds: int = Field(
        default=300,
        ge=0,
        description="TTL for in-memory recommendation cache in seconds",
    )
    cache_max_size: int = Field(
        default=128,
        ge=1,
        description="Max size of in-memory recommendation cache",
    )
    max_candidates: int = Field(default=30, ge=1, description="Max restaurants passed to the LLM")
    default_top_k: int = Field(default=5, ge=1, description="Default number of recommendations returned")
    data_cache_path: Path = Field(
        default=Path("data/cache.parquet"),
        description="Optional local Parquet cache path",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance (reload by clearing cache in tests)."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache (useful in tests)."""
    get_settings.cache_clear()
