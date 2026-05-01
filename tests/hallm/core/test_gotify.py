"""Unit tests for hallm.core.gotify."""

import httpx
import pytest

from hallm.core.gotify import GotifyClient
from hallm.core.gotify import GotifyError


def _client_with_handler(handler) -> GotifyClient:  # type: ignore[no-untyped-def]
    """Build a GotifyClient whose underlying httpx client uses the supplied handler."""

    class _Patched(GotifyClient):
        def _build_client(self) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                base_url=self._base_url,
                transport=httpx.MockTransport(handler),
            )

    return _Patched(base_url="https://gotify.test", app_token="tok")


class TestGotifyClient:
    async def test_send_returns_json(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/message"
            assert request.url.params["token"] == "tok"
            return httpx.Response(200, json={"id": 1})

        async with _client_with_handler(handler) as g:
            data = await g.send("Hi", "There")
        assert data == {"id": 1}

    async def test_send_includes_extras_when_provided(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json as _json

            captured.update(_json.loads(request.content))
            return httpx.Response(200, json={"ok": True})

        async with _client_with_handler(handler) as g:
            await g.send("t", "m", extras={"key": "val"})
        assert captured["extras"] == {"key": "val"}

    async def test_send_raises_on_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="server error")

        async with _client_with_handler(handler) as g:
            with pytest.raises(GotifyError):
                await g.send("t", "m")

    async def test_list_messages(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"messages": [{"id": 1}, {"id": 2}]})

        async with _client_with_handler(handler) as g:
            assert await g.list_messages(limit=5) == [{"id": 1}, {"id": 2}]

    async def test_delete_message(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            return httpx.Response(200)

        async with _client_with_handler(handler) as g:
            await g.delete_message(42)
        assert seen["path"] == "/message/42"

    async def test_using_outside_context_raises(self) -> None:
        client = GotifyClient(base_url="https://x", app_token="tok")
        with pytest.raises(RuntimeError, match="async context manager"):
            client._http()
