"""Smoke tests for hallm.cli.main — verifies all subcommands are wired."""

from typer.testing import CliRunner

from hallm.cli.main import app
from hallm.cli.main import main


def test_root_no_args_shows_help(runner: CliRunner) -> None:
    result = runner.invoke(app, [])
    assert result.exit_code in {0, 2}
    assert "hallm" in result.output.lower() or "usage" in result.output.lower()


def test_root_help_lists_all_subcommands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("mcp", "db", "cluster", "container", "seed", "signoz"):
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
