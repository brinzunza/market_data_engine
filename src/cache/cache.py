"""Simple in-memory cache with TTL and LRU eviction"""

import time
import threading
import sys
from typing import Any, Optional, Dict, Tuple
from collections import OrderedDict
from functools import wraps
import logging

logger = logging.getLogger(__name__)


class CacheEntry:
    """Cache entry with value and expiration time"""
    __slots__ = ('value', 'expires_at', 'created_at')

    def __init__(self, value: Any, ttl: float):
        self.value = value
        self.created_at = time.time()
        self.expires_at = self.created_at + ttl

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def age(self) -> float:
        return time.time() - self.created_at


class SimpleCache:
    """Thread-safe in-memory cache with TTL and LRU eviction"""

    def __init__(self, max_size_mb: int = 128):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._max_size_bytes = max_size_mb * 1024 * 1024

        # Metrics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._expirations = 0

        logger.info(f"Cache initialized with max size: {max_size_mb}MB")

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if exists and not expired"""
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired():
                # Remove expired entry
                del self._cache[key]
                self._expirations += 1
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl: float):
        """Set value in cache with TTL in seconds"""
        with self._lock:
            # Create entry
            entry = CacheEntry(value, ttl)

            # Remove old entry if exists
            if key in self._cache:
                del self._cache[key]

            # Add new entry
            self._cache[key] = entry

            # Check size and evict if necessary
            self._evict_if_needed()

    def delete(self, key: str) -> bool:
        """Delete specific key from cache"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self):
        """Clear all cache entries"""
        with self._lock:
            self._cache.clear()
            logger.info("Cache cleared")

    def _evict_if_needed(self):
        """Evict oldest entries if cache size exceeds limit"""
        current_size = self._estimate_size()

        while current_size > self._max_size_bytes and len(self._cache) > 0:
            # Remove oldest (first) entry
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            self._evictions += 1
            current_size = self._estimate_size()

    def _estimate_size(self) -> int:
        """Estimate cache size in bytes (rough approximation)"""
        # Simple estimation: assume ~1KB per entry on average
        # More accurate would be using sys.getsizeof recursively
        return len(self._cache) * 1024

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0

            return {
                "enabled": True,
                "entries": len(self._cache),
                "size_mb": self._estimate_size() / (1024 * 1024),
                "max_size_mb": self._max_size_bytes / (1024 * 1024),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_pct": round(hit_rate, 2),
                "evictions": self._evictions,
                "expirations": self._expirations,
                "total_requests": total_requests
            }

    def cleanup_expired(self):
        """Remove all expired entries (maintenance operation)"""
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]

            for key in expired_keys:
                del self._cache[key]
                self._expirations += 1

            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired entries")

            return len(expired_keys)


# Global cache instance
_cache_instance: Optional[SimpleCache] = None


def get_cache() -> SimpleCache:
    """Get or create global cache instance"""
    global _cache_instance
    if _cache_instance is None:
        from ..config.settings import settings
        max_size = int(getattr(settings, 'CACHE_MAX_SIZE_MB', 128))
        _cache_instance = SimpleCache(max_size_mb=max_size)
    return _cache_instance


def cache_key(*args, **kwargs) -> str:
    """Generate cache key from function arguments"""
    # Convert args and kwargs to string
    key_parts = [str(arg) for arg in args]
    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    return ":".join(key_parts)


def cached(ttl: float, key_prefix: str = ""):
    """
    Decorator for caching function results

    Args:
        ttl: Time to live in seconds
        key_prefix: Optional prefix for cache key

    Example:
        @cached(ttl=60, key_prefix="tickers")
        async def get_tickers():
            # expensive operation
            return data
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            from ..config.settings import settings

            # Check if cache is enabled
            if not getattr(settings, 'CACHE_ENABLED', True):
                return await func(*args, **kwargs)

            # Generate cache key
            key = f"{key_prefix}:{cache_key(*args, **kwargs)}" if key_prefix else cache_key(*args, **kwargs)

            # Try to get from cache
            cache = get_cache()
            cached_value = cache.get(key)

            if cached_value is not None:
                logger.debug(f"Cache hit: {key}")
                return cached_value

            # Cache miss - execute function
            logger.debug(f"Cache miss: {key}")
            result = await func(*args, **kwargs)

            # Store in cache
            cache.set(key, result, ttl)

            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            from ..config.settings import settings

            # Check if cache is enabled
            if not getattr(settings, 'CACHE_ENABLED', True):
                return func(*args, **kwargs)

            # Generate cache key
            key = f"{key_prefix}:{cache_key(*args, **kwargs)}" if key_prefix else cache_key(*args, **kwargs)

            # Try to get from cache
            cache = get_cache()
            cached_value = cache.get(key)

            if cached_value is not None:
                logger.debug(f"Cache hit: {key}")
                return cached_value

            # Cache miss - execute function
            logger.debug(f"Cache miss: {key}")
            result = func(*args, **kwargs)

            # Store in cache
            cache.set(key, result, ttl)

            return result

        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
