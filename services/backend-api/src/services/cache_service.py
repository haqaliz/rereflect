"""
Redis cache service for server-side caching.
Uses Redis DB 2 (reserved for application cache).
"""

import json
import logging
import os

import redis

logger = logging.getLogger(__name__)

_redis_cache = None
_CACHE_DISABLED = object()  # Sentinel to distinguish "not initialized" from "disabled"


def _is_cache_enabled():
    """Check if caching is enabled via environment variable."""
    return os.getenv("CACHE_ENABLED", "true").lower() == "true"


def _get_redis():
    """Get or create Redis cache client (lazy initialization)."""
    global _redis_cache
    if _redis_cache is _CACHE_DISABLED:
        return None
    if _redis_cache is None:
        if not _is_cache_enabled():
            _redis_cache = _CACHE_DISABLED
            return None
        try:
            _redis_cache = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", 6379)),
                password=os.getenv("REDIS_PASSWORD", None) or None,
                db=2,  # Reserved for application cache
                decode_responses=True,
            )
            # Test connection
            _redis_cache.ping()
        except redis.ConnectionError:
            logger.warning("Redis cache unavailable, caching disabled")
            _redis_cache = _CACHE_DISABLED
            return None
    return _redis_cache


def cache_get(key: str):
    """Get cached value, returns None on miss or if Redis is unavailable."""
    client = _get_redis()
    if client is None:
        return None
    try:
        val = client.get(key)
        return json.loads(val) if val else None
    except (redis.ConnectionError, json.JSONDecodeError):
        return None


def cache_set(key: str, value, ttl_seconds: int = 300):
    """Set cache with TTL (default 5 min)."""
    client = _get_redis()
    if client is None:
        return
    try:
        client.setex(key, ttl_seconds, json.dumps(value, default=str))
    except redis.ConnectionError:
        pass


def cache_invalidate(pattern: str):
    """Invalidate all keys matching pattern."""
    client = _get_redis()
    if client is None:
        return
    try:
        for key in client.scan_iter(match=pattern):
            client.delete(key)
    except redis.ConnectionError:
        pass
