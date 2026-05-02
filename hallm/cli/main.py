"""CLI entry-point."""

import typer

from hallm.cli.base.shell import run as _run
from hallm.cli.base.shell import run_or_fail as _run_or_fail
from hallm.cli.subcommands import cluster
from hallm.cli.subcommands import container
from hallm.cli.subcommands import db
from hallm.cli.subcommands import mcp
from hallm.cli.subcommands import secrets
from hallm.cli.subcommands import seed
from hallm.core.observability import init_observability
from hallm.core.settings import settings

app = typer.Typer(name="hallm", add_completion=False, no_args_is_help=True)
app.add_typer(mcp.app, name="mcp")
app.add_typer(db.app, name="db")
app.add_typer(cluster.app, name="cluster")
app.add_typer(secrets.app, name="secrets")
app.add_typer(container.app, name="container")
app.add_typer(seed.app, name="seed")


@app.callback()
def _callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand not in {"cluster", "seed"}:
        init_observability()


@app.command()
def install() -> None:
    """Reinstall hallm into pipx from the current source tree."""
    result = _run(["pipx", "uninstall", "hallm"])
    if result.returncode == 0:
        typer.echo("Uninstalled existing hallm from pipx.")
    _run_or_fail(
        ["pipx", "install", "--editable", str(settings.ROOT_PATH)],
        "pipx install failed",
    )
    typer.echo("hallm installed via pipx.")


def main() -> None:
    app()
