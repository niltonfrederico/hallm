"""Unit tests for hallm.core.cache."""

from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from hallm.core.cache import Cache


@pytest.fixture
def cache() -> Cache:
    return Cache(url="redis://test/0")


@pytest.fixture
def mock_client() -> AsyncMock:
    client = AsyncMock()
    client.get = AsyncMock(return_value="value")
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=2)
    client.incrby = AsyncMock(return_value=5)
    client.expire = AsyncMock(return_value=True)
    client.exists = AsyncMock(return_value=1)
    client.aclose = AsyncMock()
    return client


class TestCache:
    async def test_lazy_client_creation(self, cache: Cache) -> None:
        with patch("redis.asyncio.Redis.from_url") as factory:
            factory.return_value = AsyncMock()
            _ = cache.client
            factory.assert_called_once()

    async def test_client_is_cached(self, cache: Cache, mock_client: AsyncMock) -> None:
        with patch("redis.asyncio.Redis.from_url", return_value=mock_client) as factory:
            _ = cache.client
            _ = cache.client
            factory.assert_called_once()

    async def test_get(self, cache: Cache, mock_client: AsyncMock) -> None:
        with patch("redis.asyncio.Redis.from_url", return_value=mock_client):
            assert await cache.get("k") == "value"

    async def test_set_returns_bool(self, cache: Cache, mock_client: AsyncMock) -> None:
        with patch("redis.asyncio.Redis.from_url", return_value=mock_client):
            assert await cache.set("k", "v", ttl=60) is True
            mock_client.set.assert_awaited_once_with("k", "v", ex=60)

    async def test_delete_no_keys_returns_zero(self, cache: Cache) -> None:
        assert await cache.delete() == 0

    async def test_delete_returns_count(self, cache: Cache, mock_client: AsyncMock) -> None:
        with patch("redis.asyncio.Redis.from_url", return_value=mock_client):
            assert await cache.delete("a", "b") == 2

    async def test_incr(self, cache: Cache, mock_client: AsyncMock) -> None:
        with patch("redis.asyncio.Redis.from_url", return_value=mock_client):
            assert await cache.incr("counter", amount=2) == 5
            mock_client.incrby.assert_awaited_once_with("counter", 2)

    async def test_expire(self, cache: Cache, mock_client: AsyncMock) -> None:
        with patch("redis.asyncio.Redis.from_url", return_value=mock_client):
            assert await cache.expire("k", 30) is True

    async def test_exists(self, cache: Cache, mock_client: AsyncMock) -> None:
        with patch("redis.asyncio.Redis.from_url", return_value=mock_client):
            assert await cache.exists("k") is True

    async def test_close_when_unopened(self, cache: Cache) -> None:
        await cache.close()  # no-op

    async def test_close_when_opened(self, cache: Cache, mock_client: AsyncMock) -> None:
        with patch("redis.asyncio.Redis.from_url", return_value=mock_client):
            _ = cache.client
            await cache.close()
            mock_client.aclose.assert_awaited_once()
