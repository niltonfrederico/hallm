"""Unit tests for hallm.mcp.server."""

from unittest.mock import patch

from hallm.mcp import server


def test_mcp_instance_named_hallm() -> None:
    assert server.mcp.name == "hallm"


def test_run_invokes_fastmcp_run_with_http_transport() -> None:
    with patch.object(server.mcp, "run") as mock_run:
        server.run(host="127.0.0.1", port=9000)
    mock_run.assert_called_once_with(transport="http", host="127.0.0.1", port=9000)


def test_run_uses_defaults() -> None:
    with patch.object(server.mcp, "run") as mock_run:
        server.run()
    mock_run.assert_called_once_with(transport="http", host="0.0.0.0", port=8000)
