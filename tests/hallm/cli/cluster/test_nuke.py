"""Tests for hallm.cli.subcommands.cluster.nuke."""

from pathlib import Path
from unittest.mock import patch

import pytest

from hallm.cli.subcommands.cluster import app
from hallm.core.settings import settings
from tests.mocks import completed_process as _cp


@pytest.fixture(autouse=True)
def _set_mount(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "STORAGE_MOUNT_PATH", Path("/mnt/hallm"))


class TestNukeCommand:
    def test_yes_flag_skips_prompt(self, runner) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.nuke._docker.run_or_fail", return_value=_cp()
        ) as mock:
            result = runner.invoke(app, ["nuke", "--yes"])
        assert result.exit_code == 0
        assert "deleted" in result.output
        mock.assert_called_once()

    def test_abort_without_yes(self, runner) -> None:
        result = runner.invoke(app, ["nuke"], input="n\n")
        assert result.exit_code != 0  # typer.confirm aborts

    def test_volumes_wipes_mount(self, runner) -> None:
        with (
            patch(
                "hallm.cli.subcommands.cluster.nuke._docker.run_or_fail",
                return_value=_cp(),
            ),
            patch(
                "hallm.cli.subcommands.cluster.nuke._run_or_fail",
                return_value=_cp(),
            ) as mock_wipe,
        ):
            result = runner.invoke(app, ["nuke", "--yes", "--volumes"])
        assert result.exit_code == 0
        assert "Wiping persistent volume data" in result.output
        mock_wipe.assert_called_once()
        cmd = mock_wipe.call_args.args[0]
        assert cmd[:3] == ["sudo", "rm", "-rf"]
