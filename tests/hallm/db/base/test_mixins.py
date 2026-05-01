"""Unit tests for hallm.db.base.mixins."""

from tortoise import fields

from hallm.db.base.mixins import TimestampMixin


def test_timestamp_mixin_is_abstract() -> None:
    assert TimestampMixin._meta.abstract is True


def test_timestamp_mixin_has_uuid_pk() -> None:
    assert isinstance(TimestampMixin._meta.fields_map["id"], fields.UUIDField)
    assert TimestampMixin._meta.fields_map["id"].pk is True


def test_timestamp_mixin_has_timestamps() -> None:
    created_at = TimestampMixin._meta.fields_map["created_at"]
    updated_at = TimestampMixin._meta.fields_map["updated_at"]
    assert isinstance(created_at, fields.DatetimeField)
    assert isinstance(updated_at, fields.DatetimeField)
    assert created_at.auto_now_add is True
    assert updated_at.auto_now is True
