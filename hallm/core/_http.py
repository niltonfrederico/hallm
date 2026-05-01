"""Shared async HTTP client base for the REST integrations under :mod:`hallm.core`."""

from typing import Self

import httpx


class BaseAsyncHTTPClient:
    """Async context-manager scaffolding for httpx-backed REST clients.

    Subclasses set ``_error_class`` and override :meth:`_build_client` to
    customise headers / auth. Concrete API methods call :meth:`_http` to access
    the live client and :meth:`_check` to translate non-2xx responses into a
    typed error.
    """

    _error_class: type[Exception] = Exception

    def __init__(self, base_url: str, timeout: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)

    async def __aenter__(self) -> Self:
        self._client = self._build_client()
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(f"Use {type(self).__name__} as an async context manager.")
        return self._client

    def _check(self, response: httpx.Response) -> None:
        if response.is_error:
            raise self._error_class(f"[{response.status_code}] {response.text}")
