"""Unit tests for hallm.cli.subcommands.seed."""

from unittest.mock import patch

from typer.testing import CliRunner

from hallm.cli.subcommands.seed import app
from tests.mocks import completed_process as _cp


class TestHeimdall:
    def test_no_pod_fails(self, runner: CliRunner) -> None:
        with patch("subprocess.run", return_value=_cp(stdout="")):
            result = runner.invoke(app, [])
        assert result.exit_code == 1
        assert "No Heimdall pod" in result.output

    def test_db_not_ready_within_timeout(self, runner: CliRunner) -> None:
        with (
            patch(
                "subprocess.run",
                side_effect=[_cp(stdout="heimdall-0")] + [_cp(returncode=1)] * 100,
            ),
            patch("hallm.cli.base.poll.time.monotonic", side_effect=[0, 0, 200, 200]),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, ["--timeout", "1"])
        assert result.exit_code == 1
        assert "did not appear" in result.output

    def test_seed_success(self, runner: CliRunner) -> None:
        with (
            patch(
                "subprocess.run",
                side_effect=[
                    _cp(stdout="heimdall-0"),  # find pod
                    _cp(returncode=0, stdout="items"),  # db ready probe
                    _cp(),  # sqlite3 seed
                ],
            ),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Seeded" in result.output

    def test_sqlite_seed_fails(self, runner: CliRunner) -> None:
        with (
            patch(
                "subprocess.run",
                side_effect=[
                    _cp(stdout="heimdall-0"),
                    _cp(returncode=0, stdout="items"),
                    _cp(returncode=1, stderr="locked"),
                ],
            ),
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            result = runner.invoke(app, [])
        assert result.exit_code == 1
        assert "sqlite3 seed failed" in result.output
