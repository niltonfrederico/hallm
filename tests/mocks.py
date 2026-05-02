"""Reusable mock factories for the test suite."""

from collections.abc import Callable
from subprocess import CompletedProcess
from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import httpx


def completed_process(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> CompletedProcess[str]:
    return CompletedProcess([], returncode=returncode, stdout=stdout, stderr=stderr)


def mock_http_client(
    client_class: type,
    base_url: str,
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    auth_headers: dict[str, str] | None = None,
    **init_kwargs: Any,
) -> Any:
    """Subclass an HTTP client so its `_build_client` uses an httpx.MockTransport."""

    class _Patched(client_class):  # type: ignore[valid-type, misc]
        def _build_client(self) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                base_url=self._base_url,
                headers=auth_headers or {},
                transport=httpx.MockTransport(handler),
            )

    return _Patched(base_url=base_url, **init_kwargs)


def async_context_mock(**method_returns: object) -> AsyncMock:
    """Build an AsyncMock that works as an async context manager."""
    obj = AsyncMock()
    obj.__aenter__ = AsyncMock(return_value=obj)
    obj.__aexit__ = AsyncMock(return_value=False)
    for name, value in method_returns.items():
        setattr(obj, name, AsyncMock(return_value=value))
    return obj


def s3_session(client: AsyncMock) -> MagicMock:
    """Build a MagicMock aioboto3 Session whose `client()` returns the supplied async client."""
    session = MagicMock()
    session.client.return_value = client
    return session
