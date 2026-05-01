"""Unit tests for hallm.core._http.BaseAsyncHTTPClient."""

import httpx
import pytest

from hallm.core._http import BaseAsyncHTTPClient


class _FakeError(Exception):
    pass


class _FakeClient(BaseAsyncHTTPClient):
    _error_class = _FakeError


class TestBaseAsyncHTTPClient:
    def test_strips_trailing_slash_from_base_url(self) -> None:
        client = _FakeClient("https://api.example.com/", timeout=1.0)
        assert client._base_url == "https://api.example.com"

    async def test_context_manager_lifecycle(self) -> None:
        client = _FakeClient("https://api.example.com", timeout=1.0)
        async with client as c:
            assert c is client
            assert client._client is not None
        assert client._client is None

    async def test_http_outside_context_raises(self) -> None:
        client = _FakeClient("https://x", timeout=1.0)
        with pytest.raises(RuntimeError, match="async context manager"):
            client._http()

    async def test_check_raises_typed_error_on_4xx(self) -> None:
        client = _FakeClient("https://x", timeout=1.0)
        response = httpx.Response(404, text="not found")
        with pytest.raises(_FakeError):
            client._check(response)

    async def test_check_passes_on_2xx(self) -> None:
        client = _FakeClient("https://x", timeout=1.0)
        client._check(httpx.Response(200))
