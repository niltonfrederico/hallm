from slugify import slugify
from tortoise import Model
from tortoise import fields


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
