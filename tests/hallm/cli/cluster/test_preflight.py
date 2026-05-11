"""Tests for hallm.cli.subcommands.cluster.preflight."""

from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

import hallm.cli.subcommands.cluster.preflight as pf
from hallm.core.settings import ClusterSettings
from hallm.core.settings import settings
from tests.mocks import completed_process as _cp


class TestCheckDockerContext:
    def test_present(self) -> None:
        with patch("hallm.cli.subcommands.cluster.preflight._run", return_value=_cp()):
            ok, hint = pf._check_docker_context_exists()
        assert ok is True
        assert hint is None

    def test_missing_returns_hint(self) -> None:
        with patch("hallm.cli.subcommands.cluster.preflight._run", return_value=_cp(returncode=1)):
            ok, hint = pf._check_docker_context_exists()
        assert ok is False
        assert hint is not None and "install-rootless-docker" in hint


class TestCheckDockerDaemon:
    def test_reachable(self) -> None:
        with patch("hallm.cli.subcommands.cluster.preflight._docker.run", return_value=_cp()):
            ok, hint = pf._check_docker_daemon_reachable()
        assert ok is True
        assert hint is None

    def test_unreachable(self) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.preflight._docker.run", return_value=_cp(returncode=1)
        ):
            ok, hint = pf._check_docker_daemon_reachable()
        assert ok is False
        assert hint is not None


class TestUnprivilegedPorts:
    def test_unreadable(self) -> None:
        with patch.object(Path, "read_text", side_effect=OSError("nope")):
            ok, hint = pf._check_unprivileged_ports()
        assert ok is False
        assert hint is not None

    def test_invalid_number(self) -> None:
        with patch.object(Path, "read_text", return_value="abc\n"):
            ok, _hint = pf._check_unprivileged_ports()
        assert ok is False

    def test_allows_low_ports(self) -> None:
        with patch.object(Path, "read_text", return_value="80\n"):
            ok, hint = pf._check_unprivileged_ports()
        assert ok is True
        assert hint is None

    def test_too_restrictive(self) -> None:
        with patch.object(Path, "read_text", return_value="1024\n"):
            ok, hint = pf._check_unprivileged_ports()
        assert ok is False
        assert hint is not None


class TestCgroupDelegation:
    def test_missing_dropin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ClusterSettings, "CGROUP_DELEGATE_FILE", Path("/nonexistent-xyz"))
        ok, hint = pf._check_cgroup_delegation()
        assert ok is False
        assert hint is not None

    def test_controllers_file_unreadable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dropin = tmp_path / "delegate.conf"
        dropin.write_text("[Service]\nDelegate=cpu cpuset io\n")
        monkeypatch.setattr(ClusterSettings, "CGROUP_DELEGATE_FILE", dropin)
        with patch.object(Path, "read_text", side_effect=OSError("denied")):
            ok, _hint = pf._check_cgroup_delegation()
        assert ok is False

    def test_missing_controllers(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        dropin = tmp_path / "delegate.conf"
        dropin.write_text("ok\n")
        monkeypatch.setattr(ClusterSettings, "CGROUP_DELEGATE_FILE", dropin)
        with patch.object(Path, "read_text", return_value="cpu io"):  # missing cpuset
            ok, hint = pf._check_cgroup_delegation()
        assert ok is False
        assert hint is not None and "cpuset" in hint

    def test_all_present(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        dropin = tmp_path / "delegate.conf"
        dropin.write_text("ok\n")
        monkeypatch.setattr(ClusterSettings, "CGROUP_DELEGATE_FILE", dropin)
        with patch.object(Path, "read_text", return_value="cpu cpuset io memory"):
            ok, hint = pf._check_cgroup_delegation()
        assert ok is True
        assert hint is None


class TestGpuDevices:
    def test_all_present(self) -> None:
        with patch("hallm.cli.subcommands.cluster.preflight.os.access", return_value=True):
            ok, _hint = pf._check_gpu_devices()
        assert ok is True

    def test_missing(self) -> None:
        with patch("hallm.cli.subcommands.cluster.preflight.os.access", return_value=False):
            ok, hint = pf._check_gpu_devices()
        assert ok is False
        assert hint is not None


class TestStorageOwner:
    def test_missing_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "STORAGE_MOUNT_PATH", tmp_path / "missing")
        ok, hint = pf._check_storage_owner()
        assert ok is False
        assert hint is not None and "does not exist" in hint

    def test_wrong_owner(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        target = tmp_path / "mnt"
        target.mkdir()
        monkeypatch.setattr(settings, "STORAGE_MOUNT_PATH", target)
        with patch("hallm.cli.subcommands.cluster.preflight.os.getuid", return_value=99999):
            ok, hint = pf._check_storage_owner()
        assert ok is False
        assert hint is not None

    def test_correct_owner(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        target = tmp_path / "mnt"
        target.mkdir()
        monkeypatch.setattr(settings, "STORAGE_MOUNT_PATH", target)
        ok, _hint = pf._check_storage_owner()
        assert ok is True


class TestRunPreflight:
    def test_passes_when_all_ok(self) -> None:
        checks = (
            ("a", lambda: (True, None)),
            ("b", lambda: (True, None)),
        )
        with patch(
            "hallm.cli.subcommands.cluster.preflight._preflight_checks", return_value=checks
        ):
            pf._run_preflight()  # no exception

    def test_fails_when_any_check_fails(self) -> None:
        checks = (
            ("a", lambda: (True, None)),
            ("b", lambda: (False, "fix me")),
        )
        with (
            patch("hallm.cli.subcommands.cluster.preflight._preflight_checks", return_value=checks),
            pytest.raises(typer.Exit),
        ):
            pf._run_preflight()


class TestPreflightCommand:
    def test_invokes_run_preflight(self, runner: CliRunner) -> None:
        from hallm.cli.subcommands.cluster import app

        with patch("hallm.cli.subcommands.cluster.preflight._run_preflight") as mock_run:
            result = runner.invoke(app, ["preflight"])
        assert result.exit_code == 0
        mock_run.assert_called_once()
        assert "All preflight checks passed" in result.output
