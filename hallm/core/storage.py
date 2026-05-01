"""Async S3 client targeting RustFS."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import IO
from typing import Any
from typing import BinaryIO

import aioboto3

from hallm.core.settings import settings


@asynccontextmanager
async def s3_client() -> AsyncIterator[Any]:
    """Yield a configured aioboto3 S3 client pointing at RustFS."""
    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=settings.rustfs_endpoint,
        aws_access_key_id=settings.rustfs_access_key,
        aws_secret_access_key=settings.rustfs_secret_key,
        region_name=settings.rustfs_region,
    ) as client:
        yield client


async def ensure_bucket(bucket: str | None = None) -> None:
    """Create the configured bucket if it doesn't exist."""
    bucket = bucket or settings.rustfs_bucket
    async with s3_client() as client:
        existing = await client.list_buckets()
        names = {b["Name"] for b in existing.get("Buckets", [])}
        if bucket not in names:
            await client.create_bucket(Bucket=bucket)


async def upload_fileobj(
    key: str,
    fileobj: BinaryIO | IO[bytes],
    content_type: str | None = None,
    bucket: str | None = None,
) -> str:
    """Upload a file-like object and return its key."""
    bucket = bucket or settings.rustfs_bucket
    extra: dict[str, str] = {}
    if content_type:
        extra["ContentType"] = content_type
    async with s3_client() as client:
        await client.upload_fileobj(fileobj, bucket, key, ExtraArgs=extra or None)
    return key


async def upload_path(
    key: str,
    path: Path,
    content_type: str | None = None,
    bucket: str | None = None,
) -> str:
    """Upload a file from disk."""
    with path.open("rb") as fh:
        return await upload_fileobj(key, fh, content_type, bucket)


async def download_bytes(key: str, bucket: str | None = None) -> bytes:
    """Download an object and return its bytes."""
    bucket = bucket or settings.rustfs_bucket
    async with s3_client() as client:
        response = await client.get_object(Bucket=bucket, Key=key)
        async with response["Body"] as stream:
            return await stream.read()


async def delete(key: str, bucket: str | None = None) -> None:
    """Delete an object by key."""
    bucket = bucket or settings.rustfs_bucket
    async with s3_client() as client:
        await client.delete_object(Bucket=bucket, Key=key)


async def presigned_url(
    key: str,
    expires: int | None = None,
    bucket: str | None = None,
) -> str:
    """Return a presigned GET URL for the object."""
    bucket = bucket or settings.rustfs_bucket
    expires = expires or settings.rustfs_presign_expires
    async with s3_client() as client:
        return await client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires,
        )
