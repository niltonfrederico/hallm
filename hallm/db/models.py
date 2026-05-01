"""Tortoise ORM models for the hallm domain."""

from tortoise import fields

from hallm.core.enums import WorkTypes
from hallm.db.base.fields import ImageField
from hallm.db.base.fields import SlugField
from hallm.db.base.fields import URLField
from hallm.db.base.mixins import TimestampMixin


class FeatureFlag(TimestampMixin):
    name = fields.CharField(max_length=64)
    description = fields.TextField(default="")
    slug = SlugField(unique=True)
    enabled = fields.BooleanField(default=False)


class Library(TimestampMixin):
    name = fields.CharField(max_length=64)
    slug = SlugField(unique=True)
    work_type = fields.CharEnumField(WorkTypes, max_length=24)
    short_description = fields.CharField(max_length=300)
    full_description = fields.TextField()

    original_url = URLField(null=True)

    reviewed_at = fields.DatetimeField(null=True)

    tags = fields.ManyToManyField("models.Tag", related_name="libraries")


class Content(TimestampMixin):
    library = fields.ForeignKeyField("models.Library", related_name="contents")
    page = fields.IntField(default=1)

    text = fields.TextField()
    image = ImageField(null=True)

    tags = fields.ManyToManyField("models.Tag", related_name="contents")


class Tag(TimestampMixin):
    name = fields.CharField(max_length=64)
    slug = SlugField(unique=True)
