"""Tiny in-process TTL cache for read-heavy endpoints."""
import time


class TtlCache:
    """Least-effort TTL cache; values expire, nothing is evicted early."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._data: dict[str, tuple[float, object]] = {}

    def get(self, key: str):
        """Return the cached value or None when absent/expired."""
        hit = self._data.get(key)
        if hit is None:
            return None
        expires, value = hit
        if time.monotonic() > expires:
            self._data.pop(key, None)
            return None
        return value

    def put(self, key: str, value) -> None:
        """Store a value with the configured TTL."""
        self._data[key] = (time.monotonic() + self._ttl, value)

    def invalidate(self, key: str) -> None:
        """Drop one key (called on writes)."""
        self._data.pop(key, None)
