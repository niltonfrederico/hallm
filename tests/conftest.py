"""Pytest configuration and shared fixtures."""

import os

import pytest

from hallm.core.settings import settings

os.environ.setdefault("DATABASE_URL", "sqlite://:memory:")


_REQUIRED_DB_ENV: dict[str, str] = {
    "DATABASE_DRIVER": "postgresql",
    "POSTGRES_USER": "testuser",
    "POSTGRES_PASSWORD": "testpass",
    "POSTGRES_DB": "testdb",
    "DATABASE_HOST": "localhost",
}

_CACHED_WORKSPACE_ATTRS = ("repo_root", "k8s_path", "docker_path", "network_path")


@pytest.fixture(autouse=True)
def _reset_workspace_cache() -> None:
    """Drop any cached_property values that previous tests may have left on the singleton.

    ``Settings.repo_root`` and friends are ``@cached_property`` — once read they
    live in ``settings.__dict__`` forever. Tests that monkeypatch them leak the
    patched value through teardown because monkeypatch saves whatever oldval
    ``getattr`` returned (often a stale tmp path). Clearing __dict__ guarantees
    each test re-resolves through ``workspace.require_repo`` (or the test's own
    monkeypatch).
    """
    for attr in _CACHED_WORKSPACE_ATTRS:
        settings.__dict__.pop(attr, None)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Populate the env vars required to construct a `Settings` instance."""
    for key, val in _REQUIRED_DB_ENV.items():
        monkeypatch.setenv(key, val)
