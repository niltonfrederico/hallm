"""Cerberus PKI: either restore CA from local files or apply manifest + export."""

from pathlib import Path
from typing import ClassVar

import typer

from hallm.cli.subcommands import secrets as _secrets
from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition
from hallm.core.settings import settings


class CerberusPkiApp(App):
    """Owns k8s/cerberus.yaml so the builder's manifest-claim check passes.

    The actual install path is branched in CerberusPkiStep.run() (restore
    from local files vs apply the manifest); App.install() is used only on
    the fresh-install branch.
    """

    name: ClassVar[str] = "Cerberus PKI"
    namespace: ClassVar[str] = "cert-manager"
    manifest_path: ClassVar[Path | None] = Path("cerberus.yaml")
    wait_target: ClassVar[str | None] = "certificate/cerberus-ca"
    wait_condition: ClassVar[WaitCondition] = WaitCondition.READY
    wait_timeout: ClassVar[int] = 60


class CerberusPkiStep(Step):
    name: ClassVar[str] = "Applying Cerberus PKI"
    app: App = CerberusPkiApp()

    def __init__(self) -> None:
        self._pem_path = settings.SECRETS_PATH / "cerberus-ca.pem"
        self._key_path = settings.SECRETS_PATH / "cerberus-ca.key"
        # Branch is locked at construction so post_validate/post don't flip
        # behaviour mid-pipeline after run() creates the keys on disk.
        self._restore_mode = self._pem_path.exists() and self._key_path.exists()

    def run(self) -> None:
        if self._restore_mode:
            typer.echo(f"  Restoring Cerberus CA from {settings.SECRETS_PATH}...")
            _secrets._restore_cerberus_from_files(self._pem_path, self._key_path)
            return
        typer.echo("  Applying self-signed CA + ClusterIssuers...")
        self.app.install()

    def post_validate(self) -> None:
        # Restore path applies only the ClusterIssuer (no Certificate resource
        # to wait on); fresh-install waits for the Certificate to be Ready.
        if self._restore_mode:
            return
        super().post_validate()

    def post(self) -> None:
        if self._restore_mode:
            return
        typer.echo(f"  Exporting Cerberus CA to {settings.SECRETS_PATH}...")
        _secrets._export_cerberus_ca(self._pem_path, self._key_path)
