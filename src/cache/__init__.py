"""Cache module for in-memory caching with TTL"""

from .cache import SimpleCache, get_cache, cached

__all__ = ['SimpleCache', 'get_cache', 'cached']
