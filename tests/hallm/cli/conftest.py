"""Shared fixtures for hallm CLI tests."""

import base64
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hallm.core.settings import settings


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def k8s_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temp k8s manifests directory with a fake ollama manifest.

    Overrides the cached_property values directly on the singleton — the
    monkeypatch teardown clears them from ``settings.__dict__`` so production
    code in the same test session resolves through ``workspace.require_repo``
    again.
    """
    k8s = tmp_path / "k8s"
    k8s.mkdir()
    (k8s / "ollama.yaml").write_text("apiVersion: v1\nkind: Namespace")
    monkeypatch.setattr(settings, "repo_root", tmp_path)
    monkeypatch.setattr(settings, "k8s_path", k8s)
    monkeypatch.setattr(settings, "docker_path", tmp_path / "docker")
    monkeypatch.setattr(settings, "network_path", tmp_path / "network")
    return k8s


@pytest.fixture
def secrets_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Creates a ~/.hallm-equivalent dir in tmp_path and patches SECRETS_PATH."""
    sd = tmp_path / ".hallm"
    sd.mkdir()
    monkeypatch.setattr(settings, "SECRETS_PATH", sd)
    return sd


@pytest.fixture
def cert_b64() -> str:
    return base64.b64encode(
        b"-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----\n"
    ).decode()


@pytest.fixture
def key_b64() -> str:
    return base64.b64encode(
        b"-----BEGIN EC PRIVATE KEY-----\nfake\n-----END EC PRIVATE KEY-----\n"
    ).decode()
