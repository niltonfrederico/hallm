"""Gitea self-hosted git mirror."""

from pathlib import Path
from typing import ClassVar

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition


class GiteaApp(App):
    name: ClassVar[str] = "gitea"
    manifest_path: ClassVar[Path | None] = Path("gitea.yaml")
    wait_target: ClassVar[str | None] = "deploy/gitea"
    wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE
    wait_timeout: ClassVar[int] = 300


class GiteaStep(Step):
    name: ClassVar[str] = "Installing gitea"
    app: App = GiteaApp()
    needs_secrets: ClassVar[bool] = True
