"""Shared fixtures for cluster CLI tests."""

from pathlib import Path

import pytest

from hallm.core.settings import settings


@pytest.fixture
def fake_k8s(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temp K8S_PATH whose every required manifest exists as a stub yaml.

    Mirrors the real `k8s/` layout closely enough for build_setup_pipeline's
    manifest-claim check to pass. Tests that need a missing file delete it
    explicitly.
    """
    k8s = tmp_path / "k8s"
    k8s.mkdir()
    for name in (
        "cerberus.yaml",
        "jupyter.yaml",
        "memory-mcp.yaml",
        "paperless.yaml",
        "postgres.yaml",
        "registries.yaml",
        "rustfs.yaml",
        "traefik-config.yaml",
        "unregistry.yaml",
        "valkey.yaml",
    ):
        (k8s / name).write_text(f"# stub: {name}\n")
    (k8s / "test").mkdir()
    (k8s / "test" / "gpu-smoke.yaml").write_text("kind: Pod\n")
    (k8s / "test" / "dns-smoke.yaml").write_text("kind: Deployment\n")
    (k8s / "adhoc").mkdir()
    (k8s / "adhoc" / "cerberus-ca-issuer.yaml").write_text("kind: ClusterIssuer\n")
    (k8s / "jobs").mkdir()
    (k8s / "jobs" / "db-bootstrap.yaml").write_text("kind: Job\n")
    monkeypatch.setattr(settings, "repo_root", tmp_path)
    monkeypatch.setattr(settings, "k8s_path", k8s)
    return k8s
