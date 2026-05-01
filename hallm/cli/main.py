"""CLI entry-point."""

import typer

from hallm.cli.subcommands import container
from hallm.cli.subcommands import db
from hallm.cli.subcommands import k8s
from hallm.cli.subcommands import mcp
from hallm.core.observability import init_observability

init_observability()

app = typer.Typer(name="hallm", add_completion=False, no_args_is_help=True)
app.add_typer(mcp.app, name="mcp")
app.add_typer(db.app, name="db")
app.add_typer(k8s.app, name="k8s")
app.add_typer(container.app, name="container")


def main() -> None:
    app()
