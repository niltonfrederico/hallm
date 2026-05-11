"""Cluster lifecycle commands."""

import typer

from hallm.cli.subcommands.cluster.diagnose import diagnose
from hallm.cli.subcommands.cluster.healthcheck import healthcheck
from hallm.cli.subcommands.cluster.mount import mount
from hallm.cli.subcommands.cluster.nuke import nuke
from hallm.cli.subcommands.cluster.preflight import preflight
from hallm.cli.subcommands.cluster.setup import setup

app = typer.Typer(help="Cluster lifecycle operations.", no_args_is_help=True)

app.command()(preflight)
app.command()(diagnose)
app.command()(mount)
app.command()(setup)
app.command()(nuke)
app.command()(healthcheck)
