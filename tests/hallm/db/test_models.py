"""Schema-level tests for hallm.db.models — verifies field definitions, no DB I/O."""

from tortoise import fields

from hallm.db.base.fields import ImageField
from hallm.db.base.fields import SlugField
from hallm.db.base.fields import URLField
from hallm.db.base.mixins import TimestampMixin
from hallm.db.models import Content
from hallm.db.models import FeatureFlag
from hallm.db.models import Library
from hallm.db.models import Tag


def test_feature_flag_inherits_timestamp_mixin() -> None:
    assert issubclass(FeatureFlag, TimestampMixin)


def test_feature_flag_has_required_fields() -> None:
    assert isinstance(FeatureFlag._meta.fields_map["name"], fields.CharField)
    assert isinstance(FeatureFlag._meta.fields_map["description"], fields.TextField)
    assert isinstance(FeatureFlag._meta.fields_map["slug"], SlugField)
    assert isinstance(FeatureFlag._meta.fields_map["enabled"], fields.BooleanField)


def test_library_uses_url_field_and_slug() -> None:
    assert isinstance(Library._meta.fields_map["original_url"], URLField)
    assert isinstance(Library._meta.fields_map["slug"], SlugField)


def test_content_image_is_image_field() -> None:
    assert isinstance(Content._meta.fields_map["image"], ImageField)


def test_tag_is_concrete_model() -> None:
    assert issubclass(Tag, TimestampMixin)
    assert isinstance(Tag._meta.fields_map["slug"], SlugField)
