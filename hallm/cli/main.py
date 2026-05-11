"""CLI entry-point."""

import typer

from hallm.cli.base.shell import run as _run
from hallm.cli.base.shell import run_or_fail as _run_or_fail
from hallm.cli.subcommands import cluster
from hallm.cli.subcommands import container
from hallm.cli.subcommands import db
from hallm.cli.subcommands import mcp
from hallm.cli.subcommands import network
from hallm.cli.subcommands import secrets
from hallm.cli.subcommands import seed
from hallm.cli.subcommands import signoz
from hallm.core import workspace
from hallm.core.observability import init_observability
from hallm.core.settings import settings

app = typer.Typer(name="hallm", add_completion=False, no_args_is_help=True)
app.add_typer(mcp.app, name="mcp")
app.add_typer(db.app, name="db")
app.add_typer(cluster.app, name="cluster")
app.add_typer(secrets.app, name="secrets")
app.add_typer(container.app, name="container")
app.add_typer(seed.app, name="seed")
app.add_typer(network.app, name="network")
if settings.signoz_enabled:
    app.add_typer(signoz.app, name="signoz")


@app.callback()
def _callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand not in {"cluster", "seed", "signoz", "network"}:
        init_observability()


@app.command()
def install() -> None:
    """Reinstall hallm globally via `uv tool install --editable`.

    Records the resolved checkout path in ``~/.hallm/repo`` so workspace-bound
    commands invoked from any cwd find this checkout when env var and walk-up
    discovery both miss.
    """
    repo = workspace.require_repo()

    _run(["uv", "tool", "uninstall", "hallm"])
    _run_or_fail(
        ["uv", "tool", "install", "--editable", str(repo)],
        "uv tool install failed",
    )

    settings.SECRETS_PATH.mkdir(parents=True, exist_ok=True)
    pointer = settings.SECRETS_PATH / "repo"
    pointer.write_text(f"{repo}\n")
    typer.echo(f"hallm installed via uv tool. Repo recorded at {pointer}: {repo}")


def main() -> None:
    app()
