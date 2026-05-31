"""Deterministic restaurant filtering with relaxation (architecture §7.1, Phase P1)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from src.config import Settings, get_settings
from src.data.index import RestaurantIndex, get_index, normalize_text
from src.data.models import CostBand, Restaurant, UserPreferences

logger = logging.getLogger(__name__)

MIN_RESULTS_BEFORE_RELAX = 5
RATING_RELAX_DELTA = 0.5


@dataclass
class FilterResult:
    restaurants: list[Restaurant]
    filters_applied: dict[str, Any] = field(default_factory=dict)
    filters_relaxed: list[str] = field(default_factory=list)
    message: str | None = None
    candidates_considered: int = 0



def _adjacent_bands(budget: CostBand) -> set[CostBand]:
    if budget == CostBand.LOW:
        return {CostBand.LOW, CostBand.MEDIUM}
    if budget == CostBand.HIGH:
        return {CostBand.MEDIUM, CostBand.HIGH}
    return {CostBand.LOW, CostBand.MEDIUM, CostBand.HIGH}


def _match_location(restaurant: Restaurant, user_location: str) -> bool:
    loc = normalize_text(user_location)
    if not loc:
        return False
    return loc in restaurant.location or restaurant.location in loc


def _match_cuisine(restaurant: Restaurant, cuisine: str, *, partial: bool) -> bool:
    needle = normalize_text(cuisine)
    if not needle:
        return True
    for token in restaurant.cuisines:
        hay = normalize_text(token)
        if partial:
            if needle in hay or hay in needle:
                return True
        elif hay == needle or needle in hay.split():
            return True
    return False


def _match_budget(restaurant: Restaurant, budget: CostBand, *, relaxed: bool) -> bool:
    allowed = _adjacent_bands(budget) if relaxed else {budget}
    return restaurant.cost_band in allowed


def _match_keywords(restaurant: Restaurant, additional_preferences: str | None) -> bool:
    if not additional_preferences:
        return True
    tags = restaurant.metadata.get("tags")
    if not tags:
        return True
    keywords = [w.lower() for w in re.findall(r"\w+", additional_preferences) if len(w) >= 3]
    if not keywords:
        return True
    tag_text = " ".join(str(tag).lower() for tag in tags)
    return any(keyword in tag_text for keyword in keywords)


class FilterService:
    """Apply ordered deterministic filters with optional relaxation."""

    def __init__(
        self,
        index: RestaurantIndex | None = None,
        settings: Settings | None = None,
        *,
        min_results: int = MIN_RESULTS_BEFORE_RELAX,
    ) -> None:
        self._index = index
        self._settings = settings or get_settings()
        self._min_results = min_results

    @property
    def index(self) -> RestaurantIndex:
        if self._index is not None:
            return self._index
        return get_index()

    def filter(self, preferences: UserPreferences) -> list[Restaurant]:
        """Return capped candidate restaurants for the LLM pipeline."""
        return self.filter_with_meta(preferences).restaurants

    def recommend_filter_only(self, preferences: UserPreferences) -> list[Restaurant]:
        """Filter-only path for degraded mode (no LLM)."""
        return self.filter(preferences)

    def filter_with_meta(self, preferences: UserPreferences) -> FilterResult:
        """Filter with metadata about rules applied and relaxed."""
        index = self.index
        if not index.ready:
            raise RuntimeError("RestaurantIndex is not ready")

        location_key = normalize_text(preferences.location)
        location_scoped = [r for r in index.get_all() if _match_location(r, preferences.location)]
        filters_applied: dict[str, Any] = {
            "location": preferences.location,
            "budget": preferences.budget.value,
            "cuisine": preferences.cuisine or None,
            "min_rating": preferences.min_rating,
        }

        if not location_scoped:
            message = (
                f"No restaurants found for location '{preferences.location}'. "
                "Try a broader city or locality name."
            )
            logger.info("Filter returned 0 candidates: unknown location %r", preferences.location)
            return FilterResult([], filters_applied, [], message)

        rating_delta = 0.0
        cuisine_partial = False
        budget_relaxed = False
        filters_relaxed: list[str] = []

        candidates = self._run_pipeline(
            location_scoped,
            preferences,
            rating_delta=rating_delta,
            cuisine_partial=cuisine_partial,
            budget_relaxed=budget_relaxed,
        )

        if len(candidates) < self._min_results:
            rating_delta = RATING_RELAX_DELTA
            filters_relaxed.append("min_rating")
            candidates = self._run_pipeline(
                location_scoped,
                preferences,
                rating_delta=rating_delta,
                cuisine_partial=cuisine_partial,
                budget_relaxed=budget_relaxed,
            )
            logger.info("Relaxed min_rating by %.1f -> %d candidates", RATING_RELAX_DELTA, len(candidates))

        if len(candidates) < self._min_results:
            cuisine_partial = True
            if "cuisine_partial" not in filters_relaxed:
                filters_relaxed.append("cuisine_partial")
            candidates = self._run_pipeline(
                location_scoped,
                preferences,
                rating_delta=rating_delta,
                cuisine_partial=cuisine_partial,
                budget_relaxed=budget_relaxed,
            )
            logger.info("Relaxed cuisine to partial match -> %d candidates", len(candidates))

        if len(candidates) < self._min_results:
            budget_relaxed = True
            if "budget_adjacent" not in filters_relaxed:
                filters_relaxed.append("budget_adjacent")
            candidates = self._run_pipeline(
                location_scoped,
                preferences,
                rating_delta=rating_delta,
                cuisine_partial=cuisine_partial,
                budget_relaxed=budget_relaxed,
            )
            logger.info("Relaxed budget to adjacent bands -> %d candidates", len(candidates))

        filters_applied["min_rating"] = max(0.0, preferences.min_rating - rating_delta)
        if filters_relaxed:
            filters_applied["filters_relaxed"] = filters_relaxed

        candidates = self._apply_keyword_narrowing(candidates, preferences.additional_preferences)
        capped = self._sort_and_cap(candidates, preferences.budget)
        message = None
        if not capped:
            message = (
                f"No restaurants match your preferences in '{preferences.location}'. "
                "Try relaxing cuisine, budget, or minimum rating."
            )

        logger.info(
            "Filter complete: location=%r strict+relaxed=%s candidates=%d capped=%d",
            location_key,
            filters_relaxed or "none",
            len(candidates),
            len(capped),
        )
        return FilterResult(capped, filters_applied, filters_relaxed, message, len(candidates))

    def _run_pipeline(
        self,
        candidates: list[Restaurant],
        preferences: UserPreferences,
        *,
        rating_delta: float,
        cuisine_partial: bool,
        budget_relaxed: bool,
    ) -> list[Restaurant]:
        min_rating = max(0.0, preferences.min_rating - rating_delta)
        result: list[Restaurant] = []
        for restaurant in candidates:
            if restaurant.rating < min_rating:
                continue
            if not _match_cuisine(restaurant, preferences.cuisine, partial=cuisine_partial):
                continue
            if not _match_budget(restaurant, preferences.budget, relaxed=budget_relaxed):
                continue
            if not _match_keywords(restaurant, preferences.additional_preferences):
                continue
            result.append(restaurant)
        return result

    def _apply_keyword_narrowing(
        self,
        candidates: list[Restaurant],
        additional_preferences: str | None,
    ) -> list[Restaurant]:
        """When tags exist, keep only restaurants whose tags match preference keywords."""
        if not additional_preferences:
            return candidates
        keywords = [w.lower() for w in re.findall(r"\w+", additional_preferences) if len(w) >= 3]
        if not keywords:
            return candidates
        tagged = [r for r in candidates if r.metadata.get("tags")]
        if not tagged:
            return candidates
        matched = [
            r
            for r in candidates
            if r.metadata.get("tags") and _match_keywords(r, additional_preferences)
        ]
        return matched if matched else candidates

    def _sort_and_cap(self, candidates: list[Restaurant], budget: CostBand) -> list[Restaurant]:
        """Sort by rating (desc), then name/id; cap at MAX_CANDIDATES."""

        def sort_key(restaurant: Restaurant) -> tuple[float, float, str, str]:
            # Secondary key: cost distance from band not known per-row; use rating only
            # Tertiary: prefer matching budget band when sorting ties
            band_match = 0 if restaurant.cost_band == budget else 1
            return (-restaurant.rating, band_match, restaurant.name.lower(), restaurant.id)

        ordered = sorted(candidates, key=sort_key)
        max_candidates = self._settings.max_candidates
        return ordered[:max_candidates]
