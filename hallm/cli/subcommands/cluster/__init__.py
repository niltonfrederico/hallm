"""Cluster lifecycle commands."""

import typer

# Aliased imports keep the submodule names (cluster.preflight, cluster.setup, etc.)
# resolving to the *module*, not the function — so tests and external code can
# `import hallm.cli.subcommands.cluster.preflight` without clobbering.
from hallm.cli.subcommands.cluster.diagnose import diagnose as _diagnose
from hallm.cli.subcommands.cluster.healthcheck import healthcheck as _healthcheck
from hallm.cli.subcommands.cluster.mount import mount as _mount
from hallm.cli.subcommands.cluster.nuke import nuke as _nuke
from hallm.cli.subcommands.cluster.power import start as _start
from hallm.cli.subcommands.cluster.power import stop as _stop
from hallm.cli.subcommands.cluster.preflight import preflight as _preflight
from hallm.cli.subcommands.cluster.setup import setup as _setup

app = typer.Typer(help="Cluster lifecycle operations.", no_args_is_help=True)

app.command()(_preflight)
app.command()(_diagnose)
app.command()(_mount)
app.command()(_setup)
app.command()(_nuke)
app.command()(_healthcheck)
app.command()(_start)
app.command()(_stop)
