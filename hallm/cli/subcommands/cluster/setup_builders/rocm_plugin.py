"""ROCm Kubernetes device plugin (amd.com/gpu)."""

from typing import ClassVar

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.core.settings import ClusterSettings


class ROCmPluginApp(App):
    name: ClassVar[str] = "ROCm k8s device plugin"
    namespace: ClassVar[str] = "kube-system"
    manifest_url: ClassVar[str | None] = ClusterSettings.DEVICE_PLUGIN_URL
    # DaemonSet — readiness verified by `hallm cluster healthcheck`.


class ROCmPluginStep(Step):
    name: ClassVar[str] = "Installing ROCm k8s device plugin"
    app: App = ROCmPluginApp()
