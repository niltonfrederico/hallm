"""Pytest configuration and shared fixtures."""

import pytest

from hallm.core.settings import settings

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
