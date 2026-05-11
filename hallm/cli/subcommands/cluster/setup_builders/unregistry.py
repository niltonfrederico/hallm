"""Unregistry — push-to-cluster image registry exposed via Cerberus TLS."""

from pathlib import Path
from typing import ClassVar

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step


class UnregistryApp(App):
    name: ClassVar[str] = "Unregistry"
    namespace: ClassVar[str] = "kube-system"
    manifest_path: ClassVar[Path | None] = Path("unregistry.yaml")
    # DaemonSet — readiness verified by `hallm cluster healthcheck`.


class UnregistryStep(Step):
    name: ClassVar[str] = "Installing Unregistry"
    app: App = UnregistryApp()
