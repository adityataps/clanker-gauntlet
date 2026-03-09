"""
Redis cache helper.

Thin wrapper around redis.asyncio that handles JSON serialization,
TTL management, and a consistent key namespace.

Usage:
    from backend.data.cache import cache

    await cache.set("sleeper:projections:nfl:regular:2025:1", data, ttl=3600)
    data = await cache.get("sleeper:projections:nfl:regular:2025:1")
"""

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from backend.config import settings

logger = logging.getLogger(__name__)

# Cache TTLs (seconds)
TTL_PLAYERS = 60 * 60 * 24  # 24h — player universe rarely changes mid-season
TTL_PROJECTIONS = 60 * 60  # 1h — updated weekly but can shift
TTL_STATS = 60 * 30  # 30m — actuals during active game window
TTL_TRENDING = 60 * 15  # 15m — waiver trending moves quickly


class RedisCache:
    def __init__(self) -> None:
        self._client: aioredis.Redis | None = None

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._client

    async def get(self, key: str) -> Any | None:
        """Return the cached value or None if missing / expired."""
        try:
            r = await self._get_client()
            raw = await r.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            logger.warning("Cache GET failed for key %s", key, exc_info=True)
            return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Serialize value to JSON and store with TTL (seconds)."""
        try:
            r = await self._get_client()
            await r.set(key, json.dumps(value), ex=ttl)
        except Exception:
            logger.warning("Cache SET failed for key %s", key, exc_info=True)

    async def delete(self, key: str) -> None:
        try:
            r = await self._get_client()
            await r.delete(key)
        except Exception:
            logger.warning("Cache DELETE failed for key %s", key, exc_info=True)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# Module-level singleton — import and use directly
cache = RedisCache()
