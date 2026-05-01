"""Async client for the Gotify push-notification API."""

from typing import Any

import httpx

from hallm.core.settings import settings


class GotifyError(Exception):
    """Raised when Gotify returns an error response."""


class GotifyClient:
    """Use as an async context manager.

    >>> async with GotifyClient() as g:
    ...     await g.send("Build done", "Tests passed", priority=5)
    """

    def __init__(
        self,
        base_url: str | None = None,
        app_token: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = (base_url or settings.gotify_url).rstrip("/")
        self._token = app_token or settings.gotify_app_token
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> GotifyClient:
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Use GotifyClient as an async context manager.")
        return self._client

    def _check(self, response: httpx.Response) -> None:
        if response.is_error:
            raise GotifyError(f"[{response.status_code}] {response.text}")

    async def send(
        self,
        title: str,
        message: str,
        priority: int = 5,
        extras: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a notification via the configured app token."""
        payload: dict[str, Any] = {
            "title": title,
            "message": message,
            "priority": priority,
        }
        if extras:
            payload["extras"] = extras
        response = await self._http().post(
            "/message",
            params={"token": self._token},
            json=payload,
        )
        self._check(response)
        return response.json()

    async def list_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """List messages for the app (requires client token, not app token).

        Falls back to using the app token; for full-history reads, configure
        `GOTIFY_CLIENT_TOKEN` and pass it as `app_token` explicitly.
        """
        response = await self._http().get(
            "/message",
            params={"limit": limit, "token": self._token},
        )
        self._check(response)
        return response.json().get("messages", [])

    async def delete_message(self, message_id: int) -> None:
        response = await self._http().delete(
            f"/message/{message_id}",
            params={"token": self._token},
        )
        self._check(response)
