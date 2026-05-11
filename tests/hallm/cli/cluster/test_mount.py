"""Tests for hallm.cli.subcommands.cluster.mount."""

from pathlib import Path
from unittest.mock import patch

import pytest

import hallm.cli.subcommands.cluster.mount as mount_mod
from hallm.cli.subcommands.cluster import app
from hallm.core.settings import settings
from tests.mocks import completed_process as _cp


@pytest.fixture(autouse=True)
def _set_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "STORAGE_DEVICE", Path("/dev/sda1"))
    monkeypatch.setattr(settings, "STORAGE_MOUNT_PATH", Path("/mnt/hallm"))


class TestMountStorage:
    def test_already_mounted_skips(self) -> None:
        # findmnt returns the desired target → no umount/mkdir/mount calls.
        with patch("subprocess.run", return_value=_cp(stdout="/mnt/hallm\n")) as mock:
            mount_mod._mount_storage()
        assert mock.call_count == 1

    def test_unmounts_then_mounts(self) -> None:
        calls = [_cp(stdout="/other/path\n"), _cp(), _cp(), _cp()]
        with patch("subprocess.run", side_effect=calls) as mock:
            mount_mod._mount_storage()
        assert mock.call_count == 4

    def test_fresh_mount(self) -> None:
        calls = [_cp(stdout=""), _cp(), _cp()]  # findmnt, mkdir, mount
        with patch("subprocess.run", side_effect=calls) as mock:
            mount_mod._mount_storage()
        assert mock.call_count == 3


class TestMountCommand:
    def test_invokes_mount_storage(self, runner) -> None:
        with patch("hallm.cli.subcommands.cluster.mount._mount_storage") as mock_mount:
            result = runner.invoke(app, ["mount"])
        assert result.exit_code == 0
        mock_mount.assert_called_once()
        assert "Done" in result.output
