"""Smoke tests for hallm.cli.main — verifies all subcommands are wired."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from hallm.cli.main import app
from hallm.cli.main import main
from hallm.core import workspace
from hallm.core.settings import settings
from tests.mocks import completed_process as _cp


def test_root_no_args_shows_help(runner: CliRunner) -> None:
    result = runner.invoke(app, [])
    assert result.exit_code in {0, 2}
    assert "hallm" in result.output.lower() or "usage" in result.output.lower()


def test_root_help_lists_all_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("mcp", "db", "cluster", "container", "seed"):
        assert name in result.output


def test_cluster_subcommand_help(runner: CliRunner) -> None:
    result = runner.invoke(app, ["cluster", "--help"])
    assert result.exit_code == 0
    assert "preflight" in result.output
    assert "setup" in result.output
    assert "healthcheck" in result.output
    assert "nuke" in result.output


def test_main_function_callable() -> None:
    assert callable(main)


class TestInstall:
    def test_runs_uv_tool_install_and_writes_pointer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        repo = tmp_path / "checkout"
        repo.mkdir()
        monkeypatch.setattr(workspace, "require_repo", lambda: repo)
        monkeypatch.setattr(settings, "SECRETS_PATH", tmp_path / "hallm-home")

        with patch("subprocess.run", return_value=_cp()) as mock:
            result = runner.invoke(app, ["install"])

        assert result.exit_code == 0
        # 1st call: uv tool uninstall, 2nd: uv tool install --editable <repo>
        first_cmd = mock.call_args_list[0].args[0]
        assert first_cmd == ["uv", "tool", "uninstall", "hallm"]
        second_cmd = mock.call_args_list[1].args[0]
        assert second_cmd == ["uv", "tool", "install", "--force", "--editable", str(repo)]

        pointer = tmp_path / "hallm-home" / "repo"
        assert pointer.read_text().strip() == str(repo)

    def test_install_failure_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner: CliRunner
    ) -> None:
        repo = tmp_path / "checkout"
        repo.mkdir()
        monkeypatch.setattr(workspace, "require_repo", lambda: repo)
        monkeypatch.setattr(settings, "SECRETS_PATH", tmp_path / "hallm-home")

        # uninstall ok, install fails
        with patch("subprocess.run", side_effect=[_cp(), _cp(returncode=1, stderr="boom")]):
            result = runner.invoke(app, ["install"])

        assert result.exit_code == 1
        assert "uv tool install failed" in result.output
