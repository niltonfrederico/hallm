"""Headlamp dashboard + the in-repo hallm-links plugin."""

from pathlib import Path
from typing import ClassVar

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition
from hallm.cli.subcommands.headlamp import _build_plugin
from hallm.cli.subcommands.headlamp import _pack_configmap


class HeadlampApp(App):
    name: ClassVar[str] = "headlamp"
    namespace: ClassVar[str] = "kube-system"
    manifest_path: ClassVar[Path | None] = Path("headlamp.yaml")
    wait_target: ClassVar[str | None] = "deploy/headlamp"
    wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE
    wait_timeout: ClassVar[int] = 180


class HeadlampStep(Step):
    name: ClassVar[str] = "Installing headlamp"
    app: App = HeadlampApp()

    def pre(self) -> None:
        # Build the hallm-links plugin and pack it into the ConfigMap *before*
        # the Deployment comes up, so the volumeMount finds content on first
        # boot and we skip a rollout-restart later.
        _build_plugin()
        _pack_configmap()
