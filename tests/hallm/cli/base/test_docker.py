"""Unit tests for hallm.cli.base.docker."""

import subprocess
from unittest.mock import patch

import pytest
import typer

from hallm.cli.base import docker


def _cp(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode=returncode, stdout=stdout, stderr=stderr)


class TestContextEnv:
    def test_returns_docker_context_var(self) -> None:
        env = docker.context_env()
        assert "DOCKER_CONTEXT" in env

    def test_value_matches_settings(self) -> None:
        from hallm.core.settings import settings

        assert docker.context_env()["DOCKER_CONTEXT"] == settings.DOCKER_CONTEXT


class TestRun:
    def test_pins_docker_context_env(self) -> None:
        with patch("hallm.cli.base.shell.run", return_value=_cp()) as mock:
            docker.run(["docker", "info"])
        _, kwargs = mock.call_args
        assert "DOCKER_CONTEXT" in kwargs["env"]

    def test_returns_completed_process(self) -> None:
        cp = _cp(stdout="ok")
        with patch("hallm.cli.base.shell.run", return_value=cp):
            result = docker.run(["docker", "ps"])
        assert result is cp


class TestRunOrFail:
    def test_success_returns_process(self) -> None:
        cp = _cp(stdout="ok")
        with patch("subprocess.run", return_value=cp):
            result = docker.run_or_fail(["docker", "ps"], "should not fail")
        assert result.stdout == "ok"

    def test_failure_raises_exit(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="boom")):
            with pytest.raises(typer.Exit):
                docker.run_or_fail(["docker", "ps"], "docker failed")
