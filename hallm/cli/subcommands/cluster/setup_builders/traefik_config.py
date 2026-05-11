"""Traefik entrypoints config (postgres TCP, valkey TCP) for ingress."""

from pathlib import Path
from typing import ClassVar

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step


class TraefikConfigApp(App):
    name: ClassVar[str] = "Traefik entrypoints"
    namespace: ClassVar[str] = "kube-system"
    manifest_path: ClassVar[Path | None] = Path("traefik-config.yaml")
    # HelmChartConfig — no Deployment to wait on.


class TraefikConfigStep(Step):
    name: ClassVar[str] = "Configuring Traefik TCP entrypoints"
    app: App = TraefikConfigApp()
