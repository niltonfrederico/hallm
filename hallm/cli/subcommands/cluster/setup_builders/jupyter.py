"""Jupyter notebook deployment."""

from pathlib import Path
from typing import ClassVar

from hallm.cli.base.container import build_and_push
from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import SetupStepError
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition
from hallm.core.settings import settings

_IMAGE_NAME = "jupyter"
_DOCKERFILE_NAME = f"Dockerfile.{_IMAGE_NAME}"


class JupyterApp(App):
    name: ClassVar[str] = _IMAGE_NAME
    manifest_path: ClassVar[Path | None] = Path("jupyter.yaml")
    wait_target: ClassVar[str | None] = "deploy/jupyter"
    wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE


class JupyterStep(Step):
    name: ClassVar[str] = "Installing jupyter"
    app: App = JupyterApp()

    def pre(self) -> None:
        dockerfile = settings.docker_path / _DOCKERFILE_NAME
        if not dockerfile.exists():
            raise SetupStepError(f"Jupyter Dockerfile not found: {dockerfile}", step_name=self.name)
        build_and_push(dockerfile, _IMAGE_NAME, context=settings.repo_root)
