from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from hallm.db.base.fields import FileField
from hallm.db.base.fields import ImageField
from hallm.db.base.fields import SlugField
from hallm.db.base.fields import StoredFile
from hallm.db.base.fields import URLField


@pytest.fixture
def field() -> SlugField:
    return SlugField()


@pytest.fixture
def field_with_from() -> SlugField:
    f = SlugField()
    f.from_field = "name"
    return f


class TestSlugFieldInit:
    def test_default_max_length(self, field: SlugField) -> None:
        assert field.max_length == 60

    def test_default_null(self, field: SlugField) -> None:
        assert field.null is True

    def test_override_max_length(self) -> None:
        f = SlugField(max_length=120)
        assert f.max_length == 120

    def test_override_null(self) -> None:
        f = SlugField(null=False)
        assert f.null is False


class TestSlugFieldValidate:
    def test_no_error_when_from_field_is_none_and_value_given(self, field: SlugField) -> None:
        field.validate("hello-world")

    def test_no_error_when_from_field_set_and_value_is_none(
        self, field_with_from: SlugField
    ) -> None:
        field_with_from.validate(None)

    def test_no_error_when_from_field_set_and_value_is_empty_string(
        self, field_with_from: SlugField
    ) -> None:
        field_with_from.validate("")

    def test_raises_when_from_field_set_and_value_given(self, field_with_from: SlugField) -> None:
        with pytest.raises(ValueError, match="Cannot set slug field when from_field is set"):
            field_with_from.validate("some-slug")


class TestSlugFieldToDbValue:
    # slugify is patched because the installed `slugify` package is a Python 2
    # artifact that calls `unicode()`, which does not exist in Python 3.
    # These tests verify the routing logic of to_db_value, not the slugify library.

    def test_passes_value_directly_to_slugify(self, field: SlugField) -> None:
        with patch("hallm.db.base.fields.slugify", return_value="hello-world") as mock_slugify:
            result: str = field.to_db_value("Hello World", MagicMock())
        mock_slugify.assert_called_once_with("Hello World")
        assert result == "hello-world"

    def test_reads_from_field_attribute_before_slugifying(self, field_with_from: SlugField) -> None:
        instance: MagicMock = MagicMock()
        instance.name = "My Feature"
        with patch("hallm.db.base.fields.slugify", return_value="my-feature") as mock_slugify:
            result: str = field_with_from.to_db_value(None, instance)
        mock_slugify.assert_called_once_with("My Feature")
        assert result == "my-feature"

    def test_from_field_overrides_passed_value(self, field_with_from: SlugField) -> None:
        instance: MagicMock = MagicMock()
        instance.name = "Actual Source"
        with patch("hallm.db.base.fields.slugify", return_value="actual-source") as mock_slugify:
            result: str = field_with_from.to_db_value("ignored", instance)
        mock_slugify.assert_called_once_with("Actual Source")
        assert result == "actual-source"

    def test_returns_slugify_output(self, field: SlugField) -> None:
        with patch("hallm.db.base.fields.slugify", return_value="the-slug"):
            result: str = field.to_db_value("anything", MagicMock())
        assert result == "the-slug"


# ---------------------------------------------------------------------------
# URLField
# ---------------------------------------------------------------------------


class TestURLField:
    def test_default_max_length(self) -> None:
        f = URLField()
        assert f.max_length == 2000

    def test_validate_accepts_valid_url(self) -> None:
        URLField().validate("https://example.com")

    def test_validate_rejects_invalid_url(self) -> None:
        with pytest.raises(ValueError, match="Invalid URL"):
            URLField().validate("not a url")

    def test_validate_passes_for_empty_value(self) -> None:
        URLField().validate("")


# ---------------------------------------------------------------------------
# StoredFile
# ---------------------------------------------------------------------------


class TestStoredFile:
    def test_repr_and_str(self) -> None:
        sf = StoredFile("a/b.png", bucket="my-bucket")
        assert str(sf) == "a/b.png"
        assert repr(sf) == "StoredFile(key='a/b.png')"

    async def test_url_delegates_to_storage(self) -> None:
        sf = StoredFile("k", bucket="b")
        with patch(
            "hallm.core.storage.presigned_url", new_callable=AsyncMock, return_value="https://x"
        ) as mock:
            assert await sf.url(expires=10) == "https://x"
        mock.assert_awaited_once_with("k", expires=10, bucket="b")

    async def test_read_delegates_to_storage(self) -> None:
        sf = StoredFile("k")
        with patch(
            "hallm.core.storage.download_bytes", new_callable=AsyncMock, return_value=b"abc"
        ) as mock:
            assert await sf.read() == b"abc"
        mock.assert_awaited_once_with("k", bucket=None)

    async def test_delete_delegates_to_storage(self) -> None:
        sf = StoredFile("k")
        with patch("hallm.core.storage.delete", new_callable=AsyncMock) as mock:
            await sf.delete()
        mock.assert_awaited_once_with("k", bucket=None)


# ---------------------------------------------------------------------------
# FileField
# ---------------------------------------------------------------------------


class TestFileField:
    def test_default_kwargs(self) -> None:
        f = FileField()
        assert f.max_length == 512
        assert f.null is True
        assert f.bucket is None

    def test_custom_bucket(self) -> None:
        f = FileField(bucket="custom")
        assert f.bucket == "custom"

    def test_to_db_value_none(self) -> None:
        assert FileField().to_db_value(None, MagicMock()) is None

    def test_to_db_value_stored_file(self) -> None:
        sf = StoredFile("the/key")
        assert FileField().to_db_value(sf, MagicMock()) == "the/key"

    def test_to_db_value_str(self) -> None:
        assert FileField().to_db_value("some/key", MagicMock()) == "some/key"

    def test_to_python_value_none(self) -> None:
        assert FileField().to_python_value(None) is None

    def test_to_python_value_returns_stored_file(self) -> None:
        f = FileField(bucket="b")
        sf = f.to_python_value("some/key")
        assert isinstance(sf, StoredFile)
        assert sf.key == "some/key"
        assert sf.bucket == "b"


# ---------------------------------------------------------------------------
# ImageField
# ---------------------------------------------------------------------------


class TestImageField:
    def test_validate_accepts_image_extension(self) -> None:
        ImageField().validate("photo.png")

    def test_validate_passes_for_none(self) -> None:
        ImageField().validate(None)

    def test_validate_rejects_non_image(self) -> None:
        with pytest.raises(ValueError, match="image MIME"):
            ImageField().validate("doc.pdf")

    def test_validate_rejects_unknown_mime(self) -> None:
        with pytest.raises(ValueError, match="image MIME"):
            ImageField().validate("file.unknownext")
