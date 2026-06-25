import json
import time
from typing import Any, Optional

from app.core.config import get_settings
from app.core.logger import logger

settings = get_settings()

_redis_client = None
_memory_cache: dict[str, tuple[float, str]] = {}


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis

        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.ping()
        _redis_client = client
        logger.info("Redis cache connected at %s", settings.REDIS_URL)
        return _redis_client
    except Exception as exc:
        logger.warning("Redis unavailable (%s). Using in-memory cache fallback.", exc)
        _redis_client = False
        return None


async def cache_get(key: str) -> Optional[Any]:
    client = _get_redis()
    if client:
        raw = client.get(key)
        return json.loads(raw) if raw else None
    entry = _memory_cache.get(key)
    if not entry:
        return None
    expires_at, raw = entry
    if time.time() > expires_at:
        _memory_cache.pop(key, None)
        return None
    return json.loads(raw)


async def cache_set(key: str, value: Any, ttl: Optional[int] = None) -> None:
    ttl = ttl or settings.CACHE_TTL_SECONDS
    raw = json.dumps(value, default=str)
    client = _get_redis()
    if client:
        client.setex(key, ttl, raw)
        return
    _memory_cache[key] = (time.time() + ttl, raw)


async def cache_delete(key: str) -> None:
    client = _get_redis()
    if client:
        client.delete(key)
    _memory_cache.pop(key, None)


async def cache_delete_pattern(pattern: str) -> None:
    client = _get_redis()
    if client:
        for key in client.scan_iter(match=pattern):
            client.delete(key)
        return
    prefix = pattern.replace("*", "")
    for key in list(_memory_cache.keys()):
        if key.startswith(prefix):
            _memory_cache.pop(key, None)
