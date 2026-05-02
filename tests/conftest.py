"""Pytest configuration and shared fixtures."""

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://:memory:")


_REQUIRED_DB_ENV: dict[str, str] = {
    "DATABASE_DRIVER": "postgresql",
    "POSTGRES_USER": "testuser",
    "POSTGRES_PASSWORD": "testpass",
    "POSTGRES_DB": "testdb",
    "DATABASE_HOST": "localhost",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Populate the env vars required to construct a `Settings` instance."""
    for key, val in _REQUIRED_DB_ENV.items():
        monkeypatch.setenv(key, val)
