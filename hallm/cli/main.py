"""CLI entry-point."""

import typer

from hallm.cli.subcommands import db
from hallm.cli.subcommands import litellm
from hallm.cli.subcommands import mcp

app = typer.Typer(name="hallm", add_completion=False, invoke_without_command=True)
app.add_typer(mcp.app, name="mcp")
app.add_typer(db.app, name="db")
app.add_typer(litellm.app, name="litellm")


@app.callback()
def _root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def main() -> None:
    app()
