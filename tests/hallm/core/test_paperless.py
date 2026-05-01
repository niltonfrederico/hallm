"""Unit tests for hallm.core.paperless."""

from pathlib import Path

import httpx
import pytest

from hallm.core.paperless import PaperlessClient
from hallm.core.paperless import PaperlessError


def _client_with_handler(handler) -> PaperlessClient:  # type: ignore[no-untyped-def]
    class _Patched(PaperlessClient):
        def _build_client(self) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                base_url=self._base_url,
                headers={"Authorization": f"Token {self._token}"},
                transport=httpx.MockTransport(handler),
            )

    return _Patched(base_url="https://paperless.test", token="tok")


class TestPaperlessClient:
    async def test_upload_document_returns_response_json(self, tmp_path: Path) -> None:
        path = tmp_path / "doc.pdf"
        path.write_bytes(b"pdfdata")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/documents/post_document/"
            return httpx.Response(200, json="task-uuid-123")

        async with _client_with_handler(handler) as p:
            assert await p.upload_document(path, title="Foo", tags=[1, 2]) == "task-uuid-123"

    async def test_upload_document_with_correspondent_and_type(self, tmp_path: Path) -> None:
        path = tmp_path / "doc.pdf"
        path.write_bytes(b"x")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json="t")

        async with _client_with_handler(handler) as p:
            await p.upload_document(path, correspondent=5, document_type=7)

    async def test_list_documents_with_query(self) -> None:
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["query"] = request.url.params.get("query", "")
            return httpx.Response(200, json={"results": []})

        async with _client_with_handler(handler) as p:
            assert await p.list_documents(query="invoice") == {"results": []}
        assert captured["query"] == "invoice"

    async def test_get_document(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/documents/9/"
            return httpx.Response(200, json={"id": 9})

        async with _client_with_handler(handler) as p:
            assert await p.get_document(9) == {"id": 9}

    async def test_download_default(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/documents/3/download/"
            return httpx.Response(200, content=b"bytes")

        async with _client_with_handler(handler) as p:
            assert await p.download(3) == b"bytes"

    async def test_download_original(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["query"] = request.url.query.decode()
            return httpx.Response(200, content=b"")

        async with _client_with_handler(handler) as p:
            await p.download(3, original=True)
        assert "original=true" in seen["query"]

    async def test_delete_document(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(204)

        async with _client_with_handler(handler) as p:
            await p.delete_document(7)

    async def test_error_response_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="forbidden")

        async with _client_with_handler(handler) as p:
            with pytest.raises(PaperlessError):
                await p.get_document(1)
