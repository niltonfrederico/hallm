"""CLI entry-point."""

import typer

from hallm.cli.base.shell import run as _run
from hallm.cli.base.shell import run_or_fail as _run_or_fail
from hallm.cli.subcommands import container
from hallm.cli.subcommands import db
from hallm.cli.subcommands import k8s
from hallm.cli.subcommands import mcp
from hallm.cli.subcommands import secrets
from hallm.core.observability import init_observability
from hallm.core.settings import settings

init_observability()

app = typer.Typer(name="hallm", add_completion=False, no_args_is_help=True)
app.add_typer(mcp.app, name="mcp")
app.add_typer(db.app, name="db")
app.add_typer(k8s.app, name="k8s")
app.add_typer(secrets.app, name="secrets")
app.add_typer(container.app, name="container")


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
