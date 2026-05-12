"""Step wrapper around the SSD mount and secrets directory bootstrap."""

from typing import ClassVar

import typer

from hallm.cli.subcommands.cluster.mount import _mount_storage
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.core.settings import settings


class MountStorageStep(Step):
    name: ClassVar[str] = "Mounting SSD storage"

    def pre(self) -> None:
        settings.SECRETS_PATH.mkdir(parents=True, exist_ok=True)
        typer.echo(f"  Secrets directory: {settings.SECRETS_PATH}")
        # k3d --volume fails if the host path doesn't exist when the cluster starts.
        settings.SHARED_VOLUMES_PATH.mkdir(parents=True, exist_ok=True)
        typer.echo(f"  Shared volumes directory: {settings.SHARED_VOLUMES_PATH}")

    def run(self) -> None:
        _mount_storage()
