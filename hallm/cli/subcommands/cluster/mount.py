"""SSD storage mount management for the local cluster."""

import subprocess

import typer

from hallm.cli.base.shell import run_or_fail as _run_or_fail
from hallm.core.settings import settings


def _mount_storage() -> None:
    """Ensure STORAGE_DEVICE is mounted at STORAGE_MOUNT_PATH."""
    device = str(settings.STORAGE_DEVICE)
    mount_path = settings.STORAGE_MOUNT_PATH

    findmnt = subprocess.run(
        ["findmnt", "--source", device, "--output", "TARGET", "--noheadings"],
        text=True,
        capture_output=True,
    )
    current_mount = findmnt.stdout.strip()

    if current_mount == str(mount_path):
        typer.echo(f"  {device} already mounted at {mount_path} — skipping.")
        return

    if current_mount:
        typer.echo(f"  Unmounting {device} from {current_mount}...")
        _run_or_fail(
            ["sudo", "umount", current_mount], f"Failed to unmount {device} from {current_mount}"
        )

    typer.echo(f"  Creating mount point {mount_path}...")
    _run_or_fail(["sudo", "mkdir", "-p", str(mount_path)], f"Failed to create {mount_path}")

    typer.echo(f"  Mounting {device} at {mount_path}...")
    _run_or_fail(
        ["sudo", "mount", device, str(mount_path)], f"Failed to mount {device} at {mount_path}"
    )


def mount() -> None:
    """Mount the SSD storage device at the configured mount path."""
    typer.echo("==> Mounting SSD storage...")
    _mount_storage()
    typer.echo("Done.")
