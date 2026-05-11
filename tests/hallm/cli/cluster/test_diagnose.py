"""Tests for hallm.cli.subcommands.cluster.diagnose."""

from pathlib import Path
from unittest.mock import patch

import hallm.cli.subcommands.cluster.diagnose as diag
from hallm.cli.subcommands.cluster import app
from hallm.core.settings import settings
from tests.mocks import completed_process as _cp


class TestCgroupMemoryOk:
    def test_unreadable(self) -> None:
        with patch.object(Path, "read_text", side_effect=OSError("denied")):
            display, ok = diag._cgroup_memory_ok(1000)
        assert ok is False
        assert "cannot read" in display

    def test_unlimited(self) -> None:
        with patch.object(Path, "read_text", return_value="max\n"):
            display, ok = diag._cgroup_memory_ok(1000)
        assert ok is True
        assert display == "unlimited"

    def test_garbage_value(self) -> None:
        with patch.object(Path, "read_text", return_value="abc\n"):
            display, ok = diag._cgroup_memory_ok(1000)
        assert ok is False
        assert "unreadable" in display

    def test_high_enough(self) -> None:
        with patch.object(Path, "read_text", return_value=f"{4 * 1024 * 1024 * 1024}\n"):
            display, ok = diag._cgroup_memory_ok(1000)
        assert ok is True
        assert "4096 MB" in display

    def test_too_low(self) -> None:
        with patch.object(Path, "read_text", return_value=f"{512 * 1024 * 1024}\n"):
            display, ok = diag._cgroup_memory_ok(1000)
        assert ok is False
        assert "512 MB" in display


class TestDiagnoseCommand:
    def _all_pass(self) -> None:
        pass

    def test_all_green(self, runner, monkeypatch) -> None:
        monkeypatch.setattr(settings, "STORAGE_MOUNT_PATH", Path("/tmp"))
        with (
            patch("hallm.cli.subcommands.cluster.diagnose._docker.run", return_value=_cp()),
            patch(
                "hallm.cli.subcommands.cluster.diagnose._cgroup_memory_ok",
                return_value=("unlimited", True),
            ),
        ):
            result = runner.invoke(app, ["diagnose"])
        assert result.exit_code == 0
        assert "All diagnostic checks passed" in result.output

    def test_failure_paths(self, runner, monkeypatch) -> None:
        monkeypatch.setattr(settings, "STORAGE_MOUNT_PATH", Path("/tmp"))
        with (
            patch(
                "hallm.cli.subcommands.cluster.diagnose._docker.run",
                return_value=_cp(returncode=1, stderr="boom"),
            ),
            patch(
                "hallm.cli.subcommands.cluster.diagnose._cgroup_memory_ok",
                return_value=("256 MB", False),
            ),
        ):
            result = runner.invoke(app, ["diagnose"])
        assert result.exit_code == 1
        assert "One or more checks failed" in result.output

    def test_custom_context_overrides_setting(self, runner, monkeypatch) -> None:
        monkeypatch.setattr(settings, "DOCKER_CONTEXT", "hallm")
        monkeypatch.setattr(settings, "STORAGE_MOUNT_PATH", Path("/tmp"))
        with (
            patch("hallm.cli.subcommands.cluster.diagnose._docker.run", return_value=_cp()),
            patch(
                "hallm.cli.subcommands.cluster.diagnose._cgroup_memory_ok",
                return_value=("unlimited", True),
            ),
        ):
            result = runner.invoke(app, ["diagnose", "--context", "default"])
        assert result.exit_code == 0
        assert settings.DOCKER_CONTEXT == "default"
