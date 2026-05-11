"""Traefik entrypoints config (postgres TCP, valkey TCP) for ingress."""

from typing import ClassVar

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.core.settings import settings


class TraefikConfigApp(App):
    name: ClassVar[str] = "Traefik entrypoints"
    namespace: ClassVar[str] = "kube-system"
    manifest_path: ClassVar = settings.K8S_PATH / "traefik-config.yaml"
    # HelmChartConfig — no Deployment to wait on.


class TraefikConfigStep(Step):
    name: ClassVar[str] = "Configuring Traefik TCP entrypoints"
    app: App = TraefikConfigApp()
