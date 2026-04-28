"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
