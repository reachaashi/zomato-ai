"""In-memory thread-safe LRU cache with TTL eviction (Phase P5)."""

import hashlib
import time
from threading import Lock
from typing import Any

from src.data.models import UserPreferences


class RecommendationCache:
    """Thread-safe Least Recently Used (LRU) cache with Time-To-Live (TTL) expiration."""

    def __init__(self, max_size: int = 128, ttl_seconds: int = 300) -> None:
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, Any]] = {}
        self._access_history: list[str] = []
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        """Retrieve item if not expired. Updates LRU access ordering."""
        with self._lock:
            if key not in self._cache:
                return None

            expiry, value = self._cache[key]
            if time.time() > expiry:
                self._evict_key(key)
                return None

            # Move key to the end of access history (most recently used)
            if key in self._access_history:
                self._access_history.remove(key)
            self._access_history.append(key)
            return value

    def set(self, key: str, value: Any) -> None:
        """Store value. Evict expired or LRU item if size exceeds max_size."""
        if self.ttl_seconds <= 0:
            return

        with self._lock:
            # First, purge expired entries to free up space
            self._purge_expired()

            # If still full, evict LRU entry
            if len(self._cache) >= self.max_size and key not in self._cache:
                if self._access_history:
                    lru_key = self._access_history.pop(0)
                    self._cache.pop(lru_key, None)

            expiry = time.time() + self.ttl_seconds
            self._cache[key] = (expiry, value)
            if key in self._access_history:
                self._access_history.remove(key)
            self._access_history.append(key)

    def _evict_key(self, key: str) -> None:
        self._cache.pop(key, None)
        if key in self._access_history:
            self._access_history.remove(key)

    def _purge_expired(self) -> None:
        now = time.time()
        expired_keys = [k for k, (exp, _) in self._cache.items() if now > exp]
        for k in expired_keys:
            self._evict_key(k)

    def clear(self) -> None:
        """Clear all entries in the cache."""
        with self._lock:
            self._cache.clear()
            self._access_history.clear()


def generate_cache_key(preferences: UserPreferences, top_k: int) -> str:
    """Generate a stable sha256 cache key from UserPreferences and top_k."""
    pref_str = (
        f"{preferences.location.strip().lower()}|"
        f"{preferences.budget.value}|"
        f"{(preferences.cuisine or '').strip().lower()}|"
        f"{preferences.min_rating:.1f}|"
        f"{(preferences.additional_preferences or '').strip().lower()}|"
        f"{top_k}"
    )
    return hashlib.sha256(pref_str.encode("utf-8")).hexdigest()
