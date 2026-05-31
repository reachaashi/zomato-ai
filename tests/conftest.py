"""Shared pytest fixtures."""

import pytest

from src.config import Settings, clear_settings_cache
from src.data.index import build_index, clear_index, set_index
from src.data.models import CostBand, Restaurant


def _restaurant(
    id: str,
    name: str,
    location: str,
    cuisines: list[str],
    rating: float,
    cost: float,
    band: CostBand,
    *,
    tags: list[str] | None = None,
) -> Restaurant:
    metadata: dict = {}
    if tags:
        metadata["tags"] = tags
    return Restaurant(
        id=id,
        name=name,
        location=location,
        display_location=location,
        cuisines=cuisines,
        rating=rating,
        cost=cost,
        cost_band=band,
        metadata=metadata,
    )


@pytest.fixture
def sample_restaurants() -> list[Restaurant]:
    return [
        _restaurant("r1", "Alpha", "koramangala bangalore", ["Italian"], 4.5, 300, CostBand.LOW),
        _restaurant("r2", "Beta", "koramangala bangalore", ["Chinese"], 4.0, 600, CostBand.MEDIUM),
        _restaurant("r3", "Gamma", "indiranagar bangalore", ["Chinese"], 3.5, 600, CostBand.MEDIUM),
        _restaurant("r4", "Delta", "koramangala bangalore", ["Italian"], 4.8, 1200, CostBand.HIGH),
        _restaurant("r5", "Epsilon", "hsr bangalore", ["North Indian"], 4.2, 400, CostBand.LOW),
        _restaurant("r6", "Zeta", "koramangala bangalore", ["Mexican"], 3.0, 500, CostBand.MEDIUM),
        _restaurant(
            "r7",
            "Family Spot",
            "koramangala bangalore",
            ["Italian"],
            4.1,
            350,
            CostBand.LOW,
            tags=["rest_type:Family Dining", "family-friendly"],
        ),
    ]


@pytest.fixture
def restaurant_index(sample_restaurants: list[Restaurant]):
    clear_index()
    index = build_index(sample_restaurants)
    set_index(index)
    yield index
    clear_index()


@pytest.fixture
def filter_settings():
    clear_settings_cache()
    settings = Settings(max_candidates=30)
    yield settings
    clear_settings_cache()


@pytest.fixture(autouse=True)
def clear_recommendation_cache():
    """Clear the shared RecommendationOrchestrator cache before and after every test to prevent interference."""
    from src.services.recommender import RecommendationOrchestrator
    if getattr(RecommendationOrchestrator, "_cache_instance", None) is not None:
        RecommendationOrchestrator._cache_instance.clear()
    yield
    if getattr(RecommendationOrchestrator, "_cache_instance", None) is not None:
        RecommendationOrchestrator._cache_instance.clear()

