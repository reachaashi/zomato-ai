"""Phase 0: configuration module smoke tests."""

from pathlib import Path

from src.config import Settings, clear_settings_cache, get_settings


def test_settings_defaults():
    clear_settings_cache()
    settings = Settings()
    assert settings.hf_dataset_name == "ManikaSaini/zomato-restaurant-recommendation"
    assert settings.llm_provider == "groq"
    assert settings.llm_model == "llama-3.3-70b-versatile"
    assert settings.max_candidates == 30
    assert settings.default_top_k == 5
    assert settings.data_cache_path == Path("data/cache.parquet")


def test_get_settings_cached():
    clear_settings_cache()
    assert get_settings() is get_settings()
