"""Unit tests for the db CLI subcommand."""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from hallm.cli.subcommands.db import app
from tests.mocks import completed_process as _cp

# ---------------------------------------------------------------------------
# Fixtures local to this module
# ---------------------------------------------------------------------------


@pytest.fixture
def bootstrap_dir(tmp_path: Path) -> Path:
    """Two SQL files staged for the ConfigMap, named to verify lex ordering."""
    d = tmp_path / "bootstrap"
    d.mkdir()
    (d / "01_first.sql").write_text("SELECT 1;")
    (d / "02_second.sql").write_text("SELECT 2;")
    return d


@pytest.fixture
def job_manifest(k8s_dir: Path) -> Path:
    """A db-bootstrap.yaml under k8s_dir/jobs so .relative_to(repo_root) works."""
    jobs = k8s_dir / "jobs"
    jobs.mkdir()
    f = jobs / "db-bootstrap.yaml"
    f.write_text("apiVersion: batch/v1\nkind: Job\nmetadata:\n  name: db-bootstrap\n")
    return f


# ---------------------------------------------------------------------------
# bootstrap command
# Typer single-command apps are invoked as the default; no subcommand name.
# ---------------------------------------------------------------------------


class TestBootstrap:
    def test_no_sql_files(self, tmp_path: Path, runner: CliRunner) -> None:
        with patch("hallm.cli.subcommands.db._BOOTSTRAP_PATH", tmp_path):
            result = runner.invoke(app, [])
        assert result.exit_code == 1
        assert "No SQL files found" in result.output

    def test_happy_path_orchestrates_configmap_job_and_logs(
        self, bootstrap_dir: Path, job_manifest: Path, runner: CliRunner
    ) -> None:
        # 6 subprocess.run calls in order:
        #   1) kubectl create configmap --dry-run -o yaml
        #   2) kubectl apply -f -                         (configmap)
        #   3) kubectl delete job db-bootstrap            (prior run cleanup)
        #   4) kubectl apply -f -                         (Job manifest)
        #   5) kubectl wait --for=condition=complete ...
        #   6) kubectl logs job/db-bootstrap ...
        with (
            patch("hallm.cli.subcommands.db._BOOTSTRAP_PATH", bootstrap_dir),
            patch("hallm.cli.subcommands.db._job_manifest", return_value=job_manifest),
            patch("subprocess.run", return_value=_cp()) as mock,
        ):
            result = runner.invoke(app, [])

        assert result.exit_code == 0, result.output
        assert mock.call_count == 6
        assert "Bootstrap complete" in result.output

        configmap_cmd = mock.call_args_list[0].args[0]
        assert configmap_cmd[:3] == ["kubectl", "create", "configmap"]
        joined = " ".join(configmap_cmd)
        # Each SQL file must be staged into the ConfigMap by name.
        assert "01_first.sql=" in joined
        assert "02_second.sql=" in joined
        assert "--dry-run=client" in configmap_cmd

        delete_cmd = mock.call_args_list[2].args[0]
        assert delete_cmd[:4] == ["kubectl", "delete", "job", "db-bootstrap"]
        assert "--ignore-not-found" in delete_cmd

        wait_cmd = mock.call_args_list[4].args[0]
        assert wait_cmd[:2] == ["kubectl", "wait"]
        assert "job/db-bootstrap" in wait_cmd
        assert "--for=condition=complete" in wait_cmd

        logs_cmd = mock.call_args_list[5].args[0]
        assert logs_cmd[:2] == ["kubectl", "logs"]
        assert "job/db-bootstrap" in logs_cmd

    def test_configmap_build_failure_exits(
        self, bootstrap_dir: Path, job_manifest: Path, runner: CliRunner
    ) -> None:
        with (
            patch("hallm.cli.subcommands.db._BOOTSTRAP_PATH", bootstrap_dir),
            patch("hallm.cli.subcommands.db._job_manifest", return_value=job_manifest),
            patch("subprocess.run", return_value=_cp(returncode=1, stderr="kubectl: not found")),
        ):
            result = runner.invoke(app, [])

        assert result.exit_code == 1
        assert "Failed to build" in result.output

    def test_job_apply_failure_exits(
        self, bootstrap_dir: Path, job_manifest: Path, runner: CliRunner
    ) -> None:
        # 1) configmap dry-run OK, 2) configmap apply OK, 3) delete prior job OK,
        # 4) Job apply fails.
        calls = [_cp(), _cp(), _cp(), _cp(returncode=1, stderr="boom")]
        with (
            patch("hallm.cli.subcommands.db._BOOTSTRAP_PATH", bootstrap_dir),
            patch("hallm.cli.subcommands.db._job_manifest", return_value=job_manifest),
            patch("subprocess.run", side_effect=calls),
        ):
            result = runner.invoke(app, [])

        assert result.exit_code == 1
        assert "kubectl apply" in result.output

    def test_wait_failure_dumps_logs_and_fails(
        self, bootstrap_dir: Path, job_manifest: Path, runner: CliRunner
    ) -> None:
        # 1-4 OK; 5) wait fails; 6) logs still attempted (and succeeds).
        calls = [_cp(), _cp(), _cp(), _cp(), _cp(returncode=1, stderr="timeout"), _cp()]
        with (
            patch("hallm.cli.subcommands.db._BOOTSTRAP_PATH", bootstrap_dir),
            patch("hallm.cli.subcommands.db._job_manifest", return_value=job_manifest),
            patch("subprocess.run", side_effect=calls),
        ):
            result = runner.invoke(app, [])

        assert result.exit_code == 1
        assert "did not complete within timeout" in result.output

    def test_logs_failure_exits(
        self, bootstrap_dir: Path, job_manifest: Path, runner: CliRunner
    ) -> None:
        # Everything OK up to the log dump, which fails.
        calls = [_cp(), _cp(), _cp(), _cp(), _cp(), _cp(returncode=1, stderr="no pod")]
        with (
            patch("hallm.cli.subcommands.db._BOOTSTRAP_PATH", bootstrap_dir),
            patch("hallm.cli.subcommands.db._job_manifest", return_value=job_manifest),
            patch("subprocess.run", side_effect=calls),
        ):
            result = runner.invoke(app, [])

        assert result.exit_code == 1
        assert "Failed to read bootstrap Job logs" in result.output
