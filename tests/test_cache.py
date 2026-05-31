"""Unit tests for RecommendationCache (Phase P5)."""

import time
from src.data.models import CostBand, UserPreferences
from src.services.cache import RecommendationCache, generate_cache_key


def test_cache_set_get():
    cache = RecommendationCache(max_size=3, ttl_seconds=60)
    cache.set("k1", "v1")
    assert cache.get("k1") == "v1"
    assert cache.get("k2") is None


def test_cache_ttl_expiration():
    # Cache with 1-second TTL
    cache = RecommendationCache(max_size=3, ttl_seconds=1)
    cache.set("k1", "v1")
    assert cache.get("k1") == "v1"

    # Sleep for 1.1 seconds to expire the cache entry
    time.sleep(1.1)
    assert cache.get("k1") is None


def test_cache_lru_eviction():
    # Max size of 2
    cache = RecommendationCache(max_size=2, ttl_seconds=60)
    cache.set("k1", "v1")
    cache.set("k2", "v2")

    # Access k1 to make it most recently used
    assert cache.get("k1") == "v1"

    # Set k3, which should evict k2 (the LRU entry)
    cache.set("k3", "v3")

    assert cache.get("k1") == "v1"
    assert cache.get("k3") == "v3"
    assert cache.get("k2") is None


def test_generate_cache_key():
    prefs1 = UserPreferences(
        location="koramangala",
        budget=CostBand.LOW,
        cuisine="Italian",
        min_rating=4.0,
        additional_preferences="cozy",
    )
    prefs2 = UserPreferences(
        location=" Koramangala ",
        budget=CostBand.LOW,
        cuisine="italian",
        min_rating=4.0,
        additional_preferences="Cozy",
    )
    # Different inputs
    prefs3 = UserPreferences(
        location="koramangala",
        budget=CostBand.HIGH,
        cuisine="Italian",
        min_rating=4.0,
        additional_preferences="cozy",
    )

    key1 = generate_cache_key(prefs1, 5)
    key2 = generate_cache_key(prefs2, 5)
    key3 = generate_cache_key(prefs3, 5)

    assert key1 == key2  # Normalization makes them identical
    assert key1 != key3
