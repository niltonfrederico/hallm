"""Unit tests for hallm.core.storage."""

from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from hallm.core import storage


def _make_s3_client(**method_returns: object) -> AsyncMock:
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    for name, value in method_returns.items():
        setattr(client, name, AsyncMock(return_value=value))
    return client


def _patched_session(client: AsyncMock) -> MagicMock:
    session = MagicMock()
    session.client.return_value = client
    return session


def test_resolve_bucket_uses_explicit() -> None:
    assert storage._resolve_bucket("explicit") == "explicit"


def test_resolve_bucket_falls_back_to_settings() -> None:
    assert storage._resolve_bucket(None) == "hallm"


class TestEnsureBucket:
    async def test_creates_when_missing(self) -> None:
        client = _make_s3_client(
            list_buckets={"Buckets": []},
            create_bucket=None,
        )
        with patch("aioboto3.Session", return_value=_patched_session(client)):
            await storage.ensure_bucket("mybucket")
        client.create_bucket.assert_awaited_once_with(Bucket="mybucket")

    async def test_skips_when_exists(self) -> None:
        client = _make_s3_client(
            list_buckets={"Buckets": [{"Name": "mybucket"}]},
        )
        # Add create_bucket so we can assert it's NOT called.
        client.create_bucket = AsyncMock()
        with patch("aioboto3.Session", return_value=_patched_session(client)):
            await storage.ensure_bucket("mybucket")
        client.create_bucket.assert_not_awaited()


class TestUploadFileobj:
    async def test_returns_key(self) -> None:
        client = _make_s3_client(upload_fileobj=None)
        fh = MagicMock()
        with patch("aioboto3.Session", return_value=_patched_session(client)):
            assert await storage.upload_fileobj("k1", fh, content_type="image/png") == "k1"
        # ExtraArgs should include the content type
        _, kwargs = client.upload_fileobj.await_args
        assert kwargs["ExtraArgs"] == {"ContentType": "image/png"}

    async def test_no_content_type_passes_none_extra(self) -> None:
        client = _make_s3_client(upload_fileobj=None)
        with patch("aioboto3.Session", return_value=_patched_session(client)):
            await storage.upload_fileobj("k", MagicMock())
        _, kwargs = client.upload_fileobj.await_args
        assert kwargs["ExtraArgs"] is None


class TestUploadPath:
    async def test_opens_file_and_uploads(self, tmp_path: Path) -> None:
        path = tmp_path / "file.bin"
        path.write_bytes(b"abc")
        client = _make_s3_client(upload_fileobj=None)
        with patch("aioboto3.Session", return_value=_patched_session(client)):
            assert await storage.upload_path("thekey", path) == "thekey"
        client.upload_fileobj.assert_awaited()


class TestDownloadBytes:
    async def test_reads_body_stream(self) -> None:
        body = AsyncMock()
        body.read = AsyncMock(return_value=b"payload")
        body.__aenter__ = AsyncMock(return_value=body)
        body.__aexit__ = AsyncMock(return_value=False)
        client = _make_s3_client(get_object={"Body": body})
        with patch("aioboto3.Session", return_value=_patched_session(client)):
            assert await storage.download_bytes("k") == b"payload"


class TestDelete:
    async def test_calls_delete_object(self) -> None:
        client = _make_s3_client(delete_object=None)
        with patch("aioboto3.Session", return_value=_patched_session(client)):
            await storage.delete("k", bucket="b")
        client.delete_object.assert_awaited_once_with(Bucket="b", Key="k")


class TestPresignedUrl:
    async def test_default_expires_uses_settings(self) -> None:
        client = _make_s3_client(generate_presigned_url="https://example.com/presigned")
        with patch("aioboto3.Session", return_value=_patched_session(client)):
            url = await storage.presigned_url("k")
        assert url == "https://example.com/presigned"
        _, kwargs = client.generate_presigned_url.await_args
        from hallm.core.settings import settings

        assert kwargs["ExpiresIn"] == settings.rustfs_presign_expires

    async def test_explicit_expires(self) -> None:
        client = _make_s3_client(generate_presigned_url="https://x")
        with patch("aioboto3.Session", return_value=_patched_session(client)):
            await storage.presigned_url("k", expires=99)
        _, kwargs = client.generate_presigned_url.await_args
        assert kwargs["ExpiresIn"] == 99


@pytest.mark.parametrize(
    "fn",
    [
        storage.ensure_bucket,
        storage.delete,
        storage.download_bytes,
        storage.presigned_url,
    ],
)
async def test_default_bucket_used(fn) -> None:  # type: ignore[no-untyped-def]
    client = _make_s3_client(
        list_buckets={"Buckets": [{"Name": "hallm"}]},
        delete_object=None,
        get_object={
            "Body": (
                lambda: (
                    body := AsyncMock(),
                    setattr(body, "__aenter__", AsyncMock(return_value=body)),
                    setattr(body, "__aexit__", AsyncMock(return_value=False)),
                    setattr(body, "read", AsyncMock(return_value=b"")),
                    body,
                )[-1]
            )()
        },
        generate_presigned_url="https://x",
    )
    with patch("aioboto3.Session", return_value=_patched_session(client)):
        # Just exercise the default-bucket branch — exact return values vary by fn.
        # ensure_bucket / delete return None; download_bytes returns bytes; presigned_url returns str.
        result = await fn("k") if fn is not storage.ensure_bucket else await fn()
    if fn is storage.download_bytes:
        assert result == b""
    elif fn is storage.presigned_url:
        assert result == "https://x"
