"""
TTL-based caching for Zuora API responses.
Provides in-memory caching with automatic expiration and invalidation.
"""
import time
import hashlib
import json
import threading
from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class CacheEntry:
    """A single cache entry with value and expiration."""
    value: Any
    expires_at: float
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        return time.time() >= self.expires_at


class TTLCache:
    """
    Thread-safe TTL-based cache for Zuora API responses.

    Features:
    - Automatic expiration based on TTL
    - Cache invalidation by method/endpoint pattern
    - Cache hit/miss statistics
    - Thread-safe for concurrent access
    """

    def __init__(self, default_ttl_seconds: int = 300):
        """
        Initialize the cache.

        Args:
            default_ttl_seconds: Default time-to-live in seconds (default: 5 minutes)
        """
        self.default_ttl = default_ttl_seconds
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "invalidations": 0,
            "expirations": 0,
        }

    def _make_key(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> str:
        """
        Generate a cache key from request components.

        Args:
            method: HTTP method (GET, POST, PUT, etc.)
            endpoint: API endpoint path
            params: Query parameters
            data: Request body data

        Returns:
            Cache key string
        """
        key_parts = [method.upper(), endpoint]

        # Include params if present
        if params:
            params_str = json.dumps(params, sort_keys=True)
            params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
            key_parts.append(f"params:{params_hash}")

        # Include data if present
        if data:
            data_str = json.dumps(data, sort_keys=True)
            data_hash = hashlib.md5(data_str.encode()).hexdigest()[:8]
            key_parts.append(f"data:{data_hash}")

        return ":".join(key_parts)

    def get(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> Optional[Any]:
        """
        Retrieve a value from the cache.

        Args:
            method: HTTP method
            endpoint: API endpoint
            params: Query parameters
            data: Request body data

        Returns:
            Cached value if found and not expired, None otherwise
        """
        key = self._make_key(method, endpoint, params, data)

        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats["misses"] += 1
                return None

            if entry.is_expired():
                # Remove expired entry
                del self._cache[key]
                self._stats["misses"] += 1
                self._stats["expirations"] += 1
                return None

            self._stats["hits"] += 1
            return entry.value

    def set(
        self,
        method: str,
        endpoint: str,
        value: Any,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        ttl: Optional[int] = None
    ) -> None:
        """
        Store a value in the cache.

        Args:
            method: HTTP method
            endpoint: API endpoint
            value: Value to cache
            params: Query parameters
            data: Request body data
            ttl: Time-to-live in seconds (uses default if not specified)
        """
        key = self._make_key(method, endpoint, params, data)
        ttl_seconds = ttl if ttl is not None else self.default_ttl
        expires_at = time.time() + ttl_seconds

        with self._lock:
            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)
            self._stats["sets"] += 1

    def invalidate(self, method: Optional[str] = None, endpoint: Optional[str] = None) -> int:
        """
        Invalidate cache entries matching the given pattern.

        Args:
            method: HTTP method to match (None matches all)
            endpoint: Endpoint to match (None matches all)

        Returns:
            Number of entries invalidated
        """
        with self._lock:
            if method is None and endpoint is None:
                # Clear all
                count = len(self._cache)
                self._cache.clear()
                self._stats["invalidations"] += count
                return count

            # Pattern matching
            keys_to_remove = []
            for key in self._cache.keys():
                parts = key.split(":")
                key_method = parts[0] if len(parts) > 0 else ""
                key_endpoint = parts[1] if len(parts) > 1 else ""

                method_match = method is None or key_method == method.upper()
                endpoint_match = endpoint is None or key_endpoint.startswith(endpoint)

                if method_match and endpoint_match:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._cache[key]

            self._stats["invalidations"] += len(keys_to_remove)
            return len(keys_to_remove)

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats["invalidations"] += count

    def stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                self._stats["hits"] / total_requests * 100
                if total_requests > 0
                else 0.0
            )

            return {
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": round(hit_rate, 2),
                "sets": self._stats["sets"],
                "invalidations": self._stats["invalidations"],
                "expirations": self._stats["expirations"],
                "size": len(self._cache),
                "total_requests": total_requests,
            }

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries from the cache.

        Returns:
            Number of entries removed
        """
        with self._lock:
            current_time = time.time()
            keys_to_remove = [
                key for key, entry in self._cache.items()
                if entry.expires_at <= current_time
            ]

            for key in keys_to_remove:
                del self._cache[key]

            self._stats["expirations"] += len(keys_to_remove)
            return len(keys_to_remove)


# Global cache instance
_cache: Optional[TTLCache] = None


def get_cache() -> TTLCache:
    """Get or create the global cache instance."""
    global _cache
    if _cache is None:
        import os
        default_ttl = int(os.getenv("ZUORA_API_CACHE_TTL_SECONDS", "300"))
        _cache = TTLCache(default_ttl_seconds=default_ttl)
    return _cache
