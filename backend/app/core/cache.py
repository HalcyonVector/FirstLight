import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None
# Once a Redis call fails (e.g. no Redis configured on a free host), stop trying so
# every request doesn't pay a connection timeout. The app works fine without a cache.
_redis_disabled = False


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def cache_get(key: str) -> Any | None:
    if _redis_disabled:
        return None
    try:
        r = get_redis()
        value = await r.get(key)
    except Exception as e:  # Redis down / not configured — degrade to no cache
        _disable(e)
        return None
    if value is None:
        return None
    return json.loads(value)


async def cache_set(key: str, value: Any, ttl: int) -> None:
    if _redis_disabled:
        return
    try:
        r = get_redis()
        await r.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as e:
        _disable(e)


async def cache_incr(key: str, ttl: int) -> int | None:
    """Increment a counter (expiring ttl seconds after creation). None without Redis."""
    if _redis_disabled:
        return None
    try:
        r = get_redis()
        value = await r.incr(key)
        if value == 1:
            await r.expire(key, ttl)
        return int(value)
    except Exception as e:
        _disable(e)
        return None


async def cache_delete(key: str) -> None:
    if _redis_disabled:
        return
    try:
        r = get_redis()
        await r.delete(key)
    except Exception as e:
        _disable(e)


async def cache_delete_pattern(pattern: str) -> None:
    if _redis_disabled:
        return
    try:
        r = get_redis()
        keys = await r.keys(pattern)
        if keys:
            await r.delete(*keys)
    except Exception as e:
        _disable(e)


def _disable(err: Exception) -> None:
    """Turn caching off after the first failure so the app keeps serving."""
    global _redis_disabled
    if not _redis_disabled:
        _redis_disabled = True
        logger.warning("Redis unavailable (%s); running without cache.", err)
