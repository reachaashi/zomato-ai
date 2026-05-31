"""In-memory restaurant indexes (architecture §3.1, §4.4)."""

from __future__ import annotations

import logging
from collections import defaultdict

from src.data.models import CostBand, Restaurant

logger = logging.getLogger(__name__)

_INDEX: RestaurantIndex | None = None


def normalize_text(value: str) -> str:
    """Trim, collapse whitespace, lowercase for matching."""
    return " ".join(value.strip().lower().split())


class RestaurantIndex:
    """Queryable in-memory index built from preprocessed restaurants."""

    def __init__(self, restaurants: list[Restaurant] | None = None) -> None:
        self._all: list[Restaurant] = []
        self._by_location: dict[str, list[Restaurant]] = defaultdict(list)
        self._by_cuisine: dict[str, list[Restaurant]] = defaultdict(list)
        self._by_cost_band: dict[CostBand, list[Restaurant]] = defaultdict(list)
        self._ready = False
        if restaurants:
            self.build(restaurants)

    @property
    def ready(self) -> bool:
        return self._ready

    def build(self, restaurants: list[Restaurant]) -> None:
        """Rebuild indexes from a restaurant list."""
        self._all = list(restaurants)
        self._by_location = defaultdict(list)
        self._by_cuisine = defaultdict(list)
        self._by_cost_band = defaultdict(list)

        for restaurant in self._all:
            loc_key = normalize_text(restaurant.display_location)
            if loc_key:
                self._by_location[loc_key].append(restaurant)
            for cuisine in restaurant.cuisines:
                key = normalize_text(cuisine)
                if key:
                    self._by_cuisine[key].append(restaurant)
            self._by_cost_band[restaurant.cost_band].append(restaurant)

        self._ready = True
        logger.info(
            "RestaurantIndex built: %d restaurants, %d locations, %d cuisines",
            len(self._all),
            len(self._by_location),
            len(self._by_cuisine),
        )

    def get_all(self) -> list[Restaurant]:
        return list(self._all)

    def by_location(self, location: str) -> list[Restaurant]:
        return list(self._by_location.get(normalize_text(location), []))

    def by_cuisine(self, cuisine: str) -> list[Restaurant]:
        return list(self._by_cuisine.get(normalize_text(cuisine), []))

    def by_cost_band(self, band: CostBand) -> list[Restaurant]:
        return list(self._by_cost_band.get(band, []))

    def locations(self) -> list[str]:
        seen = set()
        unique_locs = []
        for r in self._all:
            norm = normalize_text(r.display_location)
            if norm not in seen:
                seen.add(norm)
                unique_locs.append(r.display_location)
        return sorted(unique_locs)

    def cuisines(self) -> list[str]:
        seen = set()
        unique_cuisines = []
        for r in self._all:
            for cuisine in r.cuisines:
                norm = normalize_text(cuisine)
                if norm not in seen:
                    seen.add(norm)
                    unique_cuisines.append(cuisine)
        return sorted(unique_cuisines)


def build_index(restaurants: list[Restaurant]) -> RestaurantIndex:
    """Build a new index from restaurants."""
    index = RestaurantIndex()
    index.build(restaurants)
    return index


def get_index() -> RestaurantIndex:
    """Return the process-wide index singleton."""
    global _INDEX
    if _INDEX is None or not _INDEX.ready:
        raise RuntimeError("RestaurantIndex is not loaded. Run data ingestion first.")
    return _INDEX


def set_index(index: RestaurantIndex) -> None:
    """Set the process-wide index singleton (startup or tests)."""
    global _INDEX
    _INDEX = index


def clear_index() -> None:
    """Clear the singleton (tests)."""
    global _INDEX
    _INDEX = None
