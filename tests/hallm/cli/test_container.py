"""Unit tests for hallm.cli.subcommands.container."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from hallm.cli.subcommands.container import app
from hallm.core.settings import settings as _settings

runner = CliRunner()


def _cp(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode=returncode, stdout=stdout, stderr=stderr)


def _dockerfile(tmp_path: Path, name: str) -> Path:
    dockerfile = tmp_path / "docker" / f"Dockerfile.{name}"
    dockerfile.parent.mkdir(parents=True, exist_ok=True)
    dockerfile.touch()
    return dockerfile


class TestPublish:
    def test_dockerfile_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_settings, "ROOT_PATH", tmp_path)
        result = runner.invoke(app, ["myimage"])
        assert result.exit_code == 1
        assert "Dockerfile not found" in result.output

    def test_build_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _dockerfile(tmp_path, "myimage")
        monkeypatch.setattr(_settings, "ROOT_PATH", tmp_path)
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="build error")):
            result = runner.invoke(app, ["myimage"])
        assert result.exit_code == 1
        assert "Build failed for myimage" in result.output

    def test_push_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _dockerfile(tmp_path, "myimage")
        monkeypatch.setattr(_settings, "ROOT_PATH", tmp_path)
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(),  # docker build succeeds
                _cp(returncode=1, stderr="push denied"),  # push :latest fails
            ],
        ):
            result = runner.invoke(app, ["myimage"])
        assert result.exit_code == 1
        assert "Push failed" in result.output

    def test_prune_fails_nonfatal(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _dockerfile(tmp_path, "myimage")
        monkeypatch.setattr(_settings, "ROOT_PATH", tmp_path)
        with patch(
            "subprocess.run",
            side_effect=[
                _cp(),  # docker build
                _cp(),  # push :latest
                _cp(),  # push :timestamp
                _cp(returncode=1, stderr="prune err"),  # prune fails
            ],
        ):
            result = runner.invoke(app, ["myimage"])
        assert result.exit_code == 0
        assert "WARNING" in result.output

    def test_publish_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _dockerfile(tmp_path, "myimage")
        monkeypatch.setattr(_settings, "ROOT_PATH", tmp_path)
        with patch("subprocess.run", return_value=_cp()):
            result = runner.invoke(app, ["myimage"])
        assert result.exit_code == 0
        assert "[OK]" in result.output
        assert "myimage" in result.output
        assert "latest" in result.output
