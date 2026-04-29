"""MCP subcommands."""

import typer

app = typer.Typer(help="MCP server operations.")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind"),
    port: int = typer.Option(8000, help="Port to bind"),
) -> None:
    """Start the MCP server."""
    from hallm.mcp.server import run

    run(host=host, port=port)
