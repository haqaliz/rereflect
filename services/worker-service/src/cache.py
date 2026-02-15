"""
Cache invalidation utility for worker-service.
Connects to Redis DB 2 (application cache) to invalidate stale entries
when worker tasks create or modify feedback items.
"""

import logging

import redis

from src.config import settings

logger = logging.getLogger(__name__)

_redis_cache = None
_CACHE_DISABLED = object()


def _get_redis():
    global _redis_cache
    if _redis_cache is _CACHE_DISABLED:
        return None
    if _redis_cache is None:
        try:
            _redis_cache = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password or None,
                db=2,
                decode_responses=True,
            )
            _redis_cache.ping()
        except redis.ConnectionError:
            logger.warning("Redis cache unavailable, cache invalidation disabled")
            _redis_cache = _CACHE_DISABLED
            return None
    return _redis_cache


def cache_invalidate(pattern: str):
    """Invalidate all cache keys matching pattern."""
    client = _get_redis()
    if client is None:
        return
    try:
        for key in client.scan_iter(match=pattern):
            client.delete(key)
    except redis.ConnectionError:
        pass
