"""Database initialisation helpers."""

from typing import Any

from tortoise import Tortoise

from hallm.core.settings import settings

TORTOISE_ORM: dict[str, Any] = {
    "connections": {"default": settings.database_url},
    "apps": {
        "models": {
            "models": ["hallm.db.models"],
            "default_connection": "default",
            "migrations": "hallm.db.migrations",
        }
    },
}


async def init_db() -> None:
    await Tortoise.init(config=TORTOISE_ORM)


async def close_db() -> None:
    await Tortoise.close_connections()
