"""Gotify push-notification server."""

from pathlib import Path
from typing import ClassVar

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition


class GotifyApp(App):
    name: ClassVar[str] = "gotify"
    manifest_path: ClassVar[Path | None] = Path("gotify.yaml")
    wait_target: ClassVar[str | None] = "deploy/gotify"
    wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE
    wait_timeout: ClassVar[int] = 180


class GotifyStep(Step):
    name: ClassVar[str] = "Installing gotify"
    app: App = GotifyApp()
