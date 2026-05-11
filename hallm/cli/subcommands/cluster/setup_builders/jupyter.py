"""Jupyter notebook deployment."""

from pathlib import Path
from typing import ClassVar

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition
from hallm.core.settings import settings


class JupyterApp(App):
    name: ClassVar[str] = "jupyter"
    manifest_path: ClassVar[Path | None] = settings.K8S_PATH / "jupyter.yaml"
    wait_target: ClassVar[str | None] = "deploy/jupyter"
    wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE


class JupyterStep(Step):
    name: ClassVar[str] = "Installing jupyter"
    app: App = JupyterApp()
