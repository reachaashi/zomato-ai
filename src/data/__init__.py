"""Data ingestion, models, and in-memory indexes."""

from src.data.index import (
    RestaurantIndex,
    build_index,
    clear_index,
    get_index,
    normalize_text,
    set_index,
)
from src.data.models import (
    CostBand,
    RecommendationResponse,
    RecommendationResult,
    Restaurant,
    UserPreferences,
)

__all__ = [
    "CostBand",
    "IngestionStats",
    "RecommendationResponse",
    "RecommendationResult",
    "Restaurant",
    "RestaurantIndex",
    "UserPreferences",
    "build_index",
    "clear_index",
    "get_index",
    "load_and_index",
    "load_dataset",
    "normalize_text",
    "set_index",
]


def __getattr__(name: str):
    """Lazy import ingestion to avoid circular import when running ``python -m src.data.ingestion``."""
    if name in {"IngestionStats", "load_and_index", "load_dataset"}:
        from src.data import ingestion

        return getattr(ingestion, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
