"""Thin async Valkey/Redis client wrapper."""

from typing import Any

import redis.asyncio as redis_async

from hallm.core.settings import settings


class Cache:
    """Async Valkey client backed by `redis.asyncio` (wire-compatible)."""

    def __init__(self, url: str | None = None) -> None:
        self._url = url or settings.valkey_url
        self._client: redis_async.Redis | None = None

    @property
    def client(self) -> redis_async.Redis:
        if self._client is None:
            self._client = redis_async.Redis.from_url(self._url, decode_responses=True)
        return self._client

    async def get(self, key: str) -> Any:
        return await self.client.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        return bool(await self.client.set(key, value, ex=ttl))

    async def delete(self, *keys: str) -> int:
        if not keys:
            return 0
        return int(await self.client.delete(*keys))

    async def incr(self, key: str, amount: int = 1) -> int:
        return int(await self.client.incrby(key, amount))

    async def expire(self, key: str, ttl: int) -> bool:
        return bool(await self.client.expire(key, ttl))

    async def exists(self, key: str) -> bool:
        return bool(await self.client.exists(key))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


cache = Cache()
