"""Async client for the Gotify push-notification API."""

from typing import Any

from hallm.core._http import BaseAsyncHTTPClient
from hallm.core.settings import settings


class GotifyError(Exception):
    """Raised when Gotify returns an error response."""


class GotifyClient(BaseAsyncHTTPClient):
    """Use as an async context manager.

    >>> async with GotifyClient() as g:
    ...     await g.send("Build done", "Tests passed", priority=5)
    """

    _error_class = GotifyError

    def __init__(
        self,
        base_url: str | None = None,
        app_token: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        super().__init__(base_url or settings.gotify_url, timeout)
        self._token = app_token or settings.gotify_app_token

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
