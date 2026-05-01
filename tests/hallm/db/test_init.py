"""Unit tests for hallm.db package init."""

from unittest.mock import AsyncMock
from unittest.mock import patch

from hallm import db


def test_tortoise_orm_config_shape() -> None:
    config = db.TORTOISE_ORM
    assert "connections" in config
    assert "default" in config["connections"]
    assert "apps" in config
    assert config["apps"]["models"]["models"] == ["hallm.db.models"]
    assert config["apps"]["models"]["migrations"] == "hallm.db.migrations"


async def test_init_db_calls_tortoise_init() -> None:
    with patch("hallm.db.Tortoise.init", new_callable=AsyncMock) as mock_init:
        await db.init_db()
    mock_init.assert_awaited_once_with(config=db.TORTOISE_ORM)


async def test_close_db_calls_tortoise_close_connections() -> None:
    with patch("hallm.db.Tortoise.close_connections", new_callable=AsyncMock) as mock_close:
        await db.close_db()
    mock_close.assert_awaited_once()
