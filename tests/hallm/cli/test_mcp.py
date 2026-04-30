"""Unit tests for the mcp CLI subcommand."""

from unittest.mock import patch

from typer.testing import CliRunner

from hallm.cli.subcommands.mcp import app

runner = CliRunner()

# mcp has a single @app.command(), so Typer exposes it as the root command.
# Invoke with [] (no subcommand token) to call serve directly.


def test_serve_defaults():
    with patch("hallm.mcp.server.run") as mock_run:
        result = runner.invoke(app, [])
    assert result.exit_code == 0
    mock_run.assert_called_once_with(host="0.0.0.0", port=8000)


def test_serve_custom_host():
    with patch("hallm.mcp.server.run") as mock_run:
        result = runner.invoke(app, ["--host", "127.0.0.1"])
    assert result.exit_code == 0
    mock_run.assert_called_once_with(host="127.0.0.1", port=8000)


def test_serve_custom_port():
    with patch("hallm.mcp.server.run") as mock_run:
        result = runner.invoke(app, ["--port", "9000"])
    assert result.exit_code == 0
    mock_run.assert_called_once_with(host="0.0.0.0", port=9000)


def test_serve_custom_host_and_port():
    with patch("hallm.mcp.server.run") as mock_run:
        result = runner.invoke(app, ["--host", "127.0.0.1", "--port", "9000"])
    assert result.exit_code == 0
    mock_run.assert_called_once_with(host="127.0.0.1", port=9000)
