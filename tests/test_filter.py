"""Phase P1: filter service tests."""

import pytest
from pydantic import ValidationError

from src.config import Settings
from src.data.models import CostBand, UserPreferences
from src.services.filter import FilterService, MIN_RESULTS_BEFORE_RELAX


def test_user_preferences_validation():
    prefs = UserPreferences(location="Bangalore", budget=CostBand.MEDIUM, min_rating=4.0)
    assert prefs.location == "Bangalore"
    assert prefs.min_rating == 4.0

    with pytest.raises(ValidationError):
        UserPreferences(location="", budget=CostBand.LOW)

    with pytest.raises(ValidationError):
        UserPreferences(location="X", budget=CostBand.LOW, min_rating=6.0)


def test_strict_location_filter(restaurant_index, filter_settings):
    service = FilterService(restaurant_index, filter_settings, min_results=2)
    prefs = UserPreferences(location="koramangala", budget=CostBand.LOW, min_rating=0)
    result = service.filter_with_meta(prefs)
    names = {r.name for r in result.restaurants}
    assert names == {"Alpha", "Family Spot"}
    assert all("koramangala" in r.location for r in result.restaurants)
    assert "Gamma" not in names
    assert not result.filters_relaxed


def test_strict_cuisine_budget_rating(restaurant_index, filter_settings):
    service = FilterService(restaurant_index, filter_settings, min_results=100)
    prefs = UserPreferences(
        location="koramangala",
        budget=CostBand.LOW,
        cuisine="Italian",
        min_rating=4.0,
    )
    result = service.filter(prefs)
    assert len(result) == 2
    assert all(r.cost_band == CostBand.LOW for r in result)
    assert all(any(c.lower() == "italian" for c in r.cuisines) for r in result)
    assert all(r.rating >= 4.0 for r in result)


def test_unknown_location_returns_empty_message(restaurant_index, filter_settings):
    service = FilterService(restaurant_index, filter_settings)
    prefs = UserPreferences(location="Mumbai", budget=CostBand.MEDIUM)
    result = service.filter_with_meta(prefs)
    assert result.restaurants == []
    assert result.message is not None
    assert "Mumbai" in result.message


def test_relaxation_when_few_strict_matches(restaurant_index, filter_settings):
    service = FilterService(restaurant_index, filter_settings, min_results=5)
    prefs = UserPreferences(
        location="koramangala",
        budget=CostBand.LOW,
        cuisine="Italian",
        min_rating=4.4,
    )
    result = service.filter_with_meta(prefs)
    # Strict: Alpha (4.5). Relaxed rating (-0.5) -> Family Spot (4.1) as well
    assert len(result.restaurants) >= 2
    assert "min_rating" in result.filters_relaxed
    names = {r.name for r in result.restaurants}
    assert "Alpha" in names
    assert "Family Spot" in names


def test_budget_adjacent_relaxation(restaurant_index, filter_settings):
    service = FilterService(restaurant_index, filter_settings, min_results=10)
    prefs = UserPreferences(
        location="koramangala",
        budget=CostBand.LOW,
        cuisine="Mexican",
        min_rating=2.5,
    )
    result = service.filter_with_meta(prefs)
    # Only Zeta matches cuisine; low budget strict fails (medium). Relaxation adds adjacent.
    assert any(r.name == "Zeta" for r in result.restaurants)
    assert "budget_adjacent" in result.filters_relaxed or "cuisine_partial" in result.filters_relaxed


def test_candidate_cap(restaurant_index):
    settings = Settings(max_candidates=3)
    service = FilterService(restaurant_index, settings, min_results=1)
    prefs = UserPreferences(location="bangalore", budget=CostBand.MEDIUM, min_rating=0)
    result = service.filter(prefs)
    assert len(result) <= 3
    ratings = [r.rating for r in result]
    assert ratings == sorted(ratings, reverse=True)


def test_recommend_filter_only_matches_filter(restaurant_index, filter_settings):
    service = FilterService(restaurant_index, filter_settings, min_results=1)
    prefs = UserPreferences(location="hsr", budget=CostBand.LOW, min_rating=0)
    assert service.recommend_filter_only(prefs) == service.filter(prefs)


def test_keyword_filter_on_metadata_tags(restaurant_index, filter_settings):
    service = FilterService(restaurant_index, filter_settings, min_results=1)
    prefs = UserPreferences(
        location="koramangala",
        budget=CostBand.LOW,
        min_rating=0,
        additional_preferences="family-friendly dining",
    )
    result = service.filter(prefs)
    assert len(result) == 1
    assert result[0].name == "Family Spot"
