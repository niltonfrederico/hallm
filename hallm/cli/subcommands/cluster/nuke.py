"""Cluster teardown."""

import typer

from hallm.cli.base import docker as _docker
from hallm.cli.base.shell import run_or_fail as _run_or_fail
from hallm.core.settings import ClusterSettings
from hallm.core.settings import settings


def nuke(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    volumes: bool = typer.Option(
        False,
        "--volumes",
        help="Also wipe persistent volume data from the host storage mount.",
    ),
) -> None:
    """Delete the hallm k3d cluster and all its resources.

    By default the host storage mount (PVC data) is preserved.
    Pass --volumes to also delete it.
    """
    mount_path = settings.STORAGE_MOUNT_PATH
    msg = f"This will permanently delete the '{ClusterSettings.NAME}' cluster"
    if volumes:
        msg += f" AND all data in {mount_path}"
    msg += ". Continue?"
    if not yes:
        typer.confirm(msg, abort=True)

    _docker.run_or_fail(
        ["k3d", "cluster", "delete", ClusterSettings.NAME], "k3d cluster delete failed"
    )
    typer.echo(f"\nCluster '{ClusterSettings.NAME}' deleted.")

    if volumes:
        typer.echo(f"\n==> Wiping persistent volume data at {mount_path}...")
        _run_or_fail(["sudo", "rm", "-rf", str(mount_path)], f"Failed to wipe {mount_path}")
        typer.echo("  Done.")
