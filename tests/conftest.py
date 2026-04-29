"""Pytest configuration and shared fixtures."""

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://:memory:")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
