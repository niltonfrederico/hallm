from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from hallm.db.base.fields import SlugField


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
