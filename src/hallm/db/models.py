from tortoise import fields

from hallm.db.base.fields import SlugField
from hallm.db.base.mixins import TimestampMixin


class FeatureFlag(TimestampMixin):
    name = fields.CharField()
    description = fields.TextField(default="")
    slug = SlugField(unique=True)
    enabled = fields.BooleanField(default=False)
