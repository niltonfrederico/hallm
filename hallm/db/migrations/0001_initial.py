from uuid import uuid4

from tortoise import fields
from tortoise import migrations
from tortoise.migrations import operations as ops

from hallm.db.base.fields import SlugField


class Migration(migrations.Migration):
    initial = True

    operations = [
        ops.CreateModel(
            name="FeatureFlag",
            fields=[
                (
                    "id",
                    fields.UUIDField(primary_key=True, default=uuid4, unique=True, db_index=True),
                ),
                ("created_at", fields.DatetimeField(auto_now=False, auto_now_add=True)),
                ("updated_at", fields.DatetimeField(auto_now=True, auto_now_add=False)),
                ("name", fields.CharField(max_length=64)),
                ("description", fields.TextField(default="", unique=False)),
                ("slug", SlugField(null=True, unique=True)),
                ("enabled", fields.BooleanField(default=False)),
            ],
            options={"table": "featureflag", "app": "models", "pk_attr": "id"},
            bases=["TimestampMixin"],
        ),
    ]
