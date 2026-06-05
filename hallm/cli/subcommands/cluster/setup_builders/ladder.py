"""Ladder web proxy."""

from pathlib import Path
from typing import ClassVar

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition


class LadderApp(App):
    name: ClassVar[str] = "ladder"
    manifest_path: ClassVar[Path | None] = Path("ladder.yaml")
    wait_target: ClassVar[str | None] = "deploy/ladder"
    wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE
    wait_timeout: ClassVar[int] = 180


class LadderStep(Step):
    name: ClassVar[str] = "Installing ladder"
    app: App = LadderApp()
