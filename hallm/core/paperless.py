"""Async client for the Paperless-ngx REST API."""

from pathlib import Path
from typing import Any

import httpx

from hallm.core._http import BaseAsyncHTTPClient
from hallm.core.settings import settings


class PaperlessError(Exception):
    """Raised when Paperless returns an error response."""


class PaperlessClient(BaseAsyncHTTPClient):
    """Use as an async context manager.

    >>> async with PaperlessClient() as p:
    ...     await p.upload_document(Path("invoice.pdf"), tags=["invoice"])
    """

    _error_class = PaperlessError

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(base_url or settings.paperless_url, timeout)
        self._token = token or settings.paperless_token

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Token {self._token}"},
            timeout=self._timeout,
        )

    async def upload_document(
        self,
        path: Path,
        title: str | None = None,
        tags: list[int] | None = None,
        correspondent: int | None = None,
        document_type: int | None = None,
    ) -> str:
        """Submit a document for ingestion. Returns the async task UUID."""
        data: dict[str, Any] = {}
        if title:
            data["title"] = title
        if tags:
            for tag_id in tags:
                data.setdefault("tags", []).append(tag_id)
        if correspondent is not None:
            data["correspondent"] = correspondent
        if document_type is not None:
            data["document_type"] = document_type

        with path.open("rb") as fh:
            response = await self._http().post(
                "/api/documents/post_document/",
                files={"document": (path.name, fh)},
                data=data,
            )
        self._check(response)
        return response.json()

    async def list_documents(
        self,
        query: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if query:
            params["query"] = query
        response = await self._http().get("/api/documents/", params=params)
        self._check(response)
        return response.json()

    async def get_document(self, document_id: int) -> dict[str, Any]:
        response = await self._http().get(f"/api/documents/{document_id}/")
        self._check(response)
        return response.json()

    async def download(self, document_id: int, original: bool = False) -> bytes:
        suffix = "/download/" + ("?original=true" if original else "")
        response = await self._http().get(f"/api/documents/{document_id}{suffix}")
        self._check(response)
        return response.content

    async def delete_document(self, document_id: int) -> None:
        response = await self._http().delete(f"/api/documents/{document_id}/")
        self._check(response)
