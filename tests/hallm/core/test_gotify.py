"""Unit tests for hallm.core.gotify."""

import json
from collections.abc import Callable

import httpx
import pytest

from hallm.core.gotify import GotifyClient
from hallm.core.gotify import GotifyError
from tests.mocks import mock_http_client


def _gotify_client(handler: Callable[[httpx.Request], httpx.Response]) -> GotifyClient:
    return mock_http_client(
        GotifyClient,
        base_url="https://gotify.test",
        handler=handler,
        app_token="tok",
    )


class TestGotifyClient:
    async def test_send_returns_json(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/message"
            assert request.url.params["token"] == "tok"
            return httpx.Response(200, json={"id": 1})

        async with _gotify_client(handler) as g:
            data = await g.send("Hi", "There")
        assert data == {"id": 1}

    async def test_send_includes_extras_when_provided(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(200, json={"ok": True})

        async with _gotify_client(handler) as g:
            await g.send("t", "m", extras={"key": "val"})
        assert captured["extras"] == {"key": "val"}

    async def test_send_raises_on_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="server error")

        async with _gotify_client(handler) as g:
            with pytest.raises(GotifyError):
                await g.send("t", "m")

    async def test_list_messages(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"messages": [{"id": 1}, {"id": 2}]})

        async with _gotify_client(handler) as g:
            assert await g.list_messages(limit=5) == [{"id": 1}, {"id": 2}]

    async def test_delete_message(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            return httpx.Response(200)

        async with _gotify_client(handler) as g:
            await g.delete_message(42)
        assert seen["path"] == "/message/42"

    async def test_using_outside_context_raises(self) -> None:
        client = GotifyClient(base_url="https://x", app_token="tok")
        with pytest.raises(RuntimeError, match="async context manager"):
            client._http()
