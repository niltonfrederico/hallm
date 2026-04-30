"""Unit tests for the db CLI subcommand."""

from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import patch

import asyncpg
from typer.testing import CliRunner

from hallm.cli.subcommands.db import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# bootstrap command
# Typer single-command apps are invoked as the default; no subcommand name.
# ---------------------------------------------------------------------------


def _make_conn() -> AsyncMock:
    """Return an AsyncMock that works as an async context manager."""
    conn = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)
    return conn


class TestBootstrap:
    def test_no_sql_files(self, tmp_path: Path) -> None:
        with patch("hallm.cli.subcommands.db._BOOTSTRAP_PATH", tmp_path):
            result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "No SQL files found" in result.output

    def test_runs_each_sql_file_in_order(self, tmp_path: Path) -> None:
        (tmp_path / "01_schemas.sql").write_text("CREATE SCHEMA IF NOT EXISTS hallm;")
        (tmp_path / "02_grants.sql").write_text("GRANT USAGE ON SCHEMA hallm TO hallm;")
        conn = _make_conn()

        with (
            patch("hallm.cli.subcommands.db._BOOTSTRAP_PATH", tmp_path),
            patch("hallm.cli.subcommands.db._substitutions", return_value={}),
            patch("asyncpg.connect", AsyncMock(return_value=conn)),
        ):
            result = runner.invoke(app, [])

        assert result.exit_code == 0, result.output
        assert conn.execute.await_count == 2
        calls = [c.args[0] for c in conn.execute.await_args_list]
        assert "CREATE SCHEMA" in calls[0]
        assert "GRANT USAGE" in calls[1]

    def test_substitutes_placeholders_in_sql(self, tmp_path: Path) -> None:
        (tmp_path / "init.sql").write_text("PASSWORD '##POSTGRES_PASSWORD##'")
        conn = _make_conn()

        with (
            patch("hallm.cli.subcommands.db._BOOTSTRAP_PATH", tmp_path),
            patch(
                "hallm.cli.subcommands.db._substitutions",
                return_value={"POSTGRES_PASSWORD": "s3cr3t"},
            ),
            patch("asyncpg.connect", AsyncMock(return_value=conn)),
        ):
            runner.invoke(app, [])

        executed_sql = conn.execute.await_args_list[0].args[0]
        assert "s3cr3t" in executed_sql
        assert "##POSTGRES_PASSWORD##" not in executed_sql

    def test_reports_bootstrap_complete_on_success(self, tmp_path: Path) -> None:
        (tmp_path / "init.sql").write_text("SELECT 1;")
        conn = _make_conn()

        with (
            patch("hallm.cli.subcommands.db._BOOTSTRAP_PATH", tmp_path),
            patch("hallm.cli.subcommands.db._substitutions", return_value={}),
            patch("asyncpg.connect", AsyncMock(return_value=conn)),
        ):
            result = runner.invoke(app, [])

        assert result.exit_code == 0
        assert "Bootstrap complete" in result.output

    def test_connection_os_error_exits_with_1(self, tmp_path: Path) -> None:
        (tmp_path / "init.sql").write_text("SELECT 1;")

        with (
            patch("hallm.cli.subcommands.db._BOOTSTRAP_PATH", tmp_path),
            patch("hallm.cli.subcommands.db._substitutions", return_value={}),
            patch("asyncpg.connect", AsyncMock(side_effect=OSError("refused"))),
        ):
            result = runner.invoke(app, [])

        assert result.exit_code == 1
        assert "Cannot reach database" in result.output

    def test_postgres_error_exits_with_1(self, tmp_path: Path) -> None:
        (tmp_path / "init.sql").write_text("SELECT 1;")

        with (
            patch("hallm.cli.subcommands.db._BOOTSTRAP_PATH", tmp_path),
            patch("hallm.cli.subcommands.db._substitutions", return_value={}),
            patch(
                "asyncpg.connect",
                AsyncMock(side_effect=asyncpg.InvalidPasswordError("bad password")),
            ),
        ):
            result = runner.invoke(app, [])

        assert result.exit_code == 1
        assert "Database connection failed" in result.output

    def test_unknown_placeholder_exits_with_1(self, tmp_path: Path) -> None:
        (tmp_path / "init.sql").write_text("##UNKNOWN_KEY##")
        conn = _make_conn()

        with (
            patch("hallm.cli.subcommands.db._BOOTSTRAP_PATH", tmp_path),
            patch("hallm.cli.subcommands.db._substitutions", return_value={}),
            patch("asyncpg.connect", AsyncMock(return_value=conn)),
        ):
            result = runner.invoke(app, [])

        assert result.exit_code == 1
        assert "UNKNOWN_KEY" in result.output
