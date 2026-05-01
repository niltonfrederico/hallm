import mimetypes

import validators
from slugify import slugify
from tortoise import Model
from tortoise import fields

from hallm.core import storage


class SlugField(fields.CharField):
    from_field: str | None = None

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("max_length", 60)
        kwargs.setdefault("null", True)
        super().__init__(*args, **kwargs)

    def validate(self, value: str) -> None:
        super().validate(value)

        # Can't use value with from_field set
        if self.from_field and value:
            raise ValueError("Cannot set slug field when from_field is set")

    def to_db_value(self, value: str, instance: type[Model] | Model) -> str:
        if self.from_field:
            value = getattr(instance, self.from_field)

        return slugify(value)


class URLField(fields.CharField):
    accepted_schemes = ("http://", "https://", "ftp://", "ftps://")

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("max_length", 2000)
        super().__init__(*args, **kwargs)

    def validate(self, value: str) -> None:
        super().validate(value)

        if value and not validators.url(value):
            raise ValueError("Invalid URL")


class StoredFile:
    """Lightweight handle to an object stored in RustFS.

    Stored as the S3 key in the database; provides async helpers for
    download/presign/delete on top of `hallm.core.storage`.
    """

    __slots__ = ("bucket", "key")

    def __init__(self, key: str, bucket: str | None = None) -> None:
        self.key = key
        self.bucket = bucket

    def __str__(self) -> str:
        return self.key

    def __repr__(self) -> str:
        return f"StoredFile(key={self.key!r})"

    async def url(self, expires: int | None = None) -> str:
        return await storage.presigned_url(self.key, expires=expires, bucket=self.bucket)

    async def read(self) -> bytes:
        return await storage.download_bytes(self.key, bucket=self.bucket)

    async def delete(self) -> None:
        await storage.delete(self.key, bucket=self.bucket)


class FileField(fields.CharField):
    """Stores an S3 key (in RustFS) and exposes a `StoredFile` handle.

    The field never uploads on its own — call `storage.upload_*` first, then
    assign the resulting key to the model attribute.
    """

    def __init__(self, *args, bucket: str | None = None, **kwargs) -> None:
        kwargs.setdefault("max_length", 512)
        kwargs.setdefault("null", True)
        self.bucket = bucket
        super().__init__(*args, **kwargs)

    def to_db_value(
        self, value: str | StoredFile | None, instance: type[Model] | Model
    ) -> str | None:
        if value is None:
            return None
        if isinstance(value, StoredFile):
            return value.key
        return value

    def to_python_value(self, value: str | None) -> StoredFile | None:
        if value is None:
            return None
        return StoredFile(value, bucket=self.bucket)


class ImageField(FileField):
    """File field that rejects non-image content types on validation."""

    def validate(self, value: str | StoredFile | None) -> None:
        super().validate(value)
        if value is None:
            return
        key = value.key if isinstance(value, StoredFile) else value
        mime, _ = mimetypes.guess_type(key)
        if mime is None or not mime.startswith("image/"):
            raise ValueError(f"ImageField requires an image MIME type, got {mime!r} for {key!r}")
