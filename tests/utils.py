"""Shared data factories for the test suite."""

from pathlib import Path


def write_dockerfile(tmp_path: Path, name: str) -> Path:
    dockerfile = tmp_path / "docker" / f"Dockerfile.{name}"
    dockerfile.parent.mkdir(parents=True, exist_ok=True)
    dockerfile.touch()
    return dockerfile


def write_manifest(tmp_path: Path, name: str) -> Path:
    k8s = tmp_path / "k8s"
    k8s.mkdir(exist_ok=True)
    manifest = k8s / f"{name}.yaml"
    manifest.write_text("apiVersion: v1\nkind: Namespace")
    return manifest
