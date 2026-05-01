"""MCP server powered by FastMCP."""

from fastmcp import FastMCP

from hallm.core.observability import init_observability

init_observability()

mcp = FastMCP("hallm")


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    mcp.run(transport="http", host=host, port=port)
