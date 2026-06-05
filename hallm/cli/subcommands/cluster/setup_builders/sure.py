"""Sure self-hosted finance app (web + worker)."""

from pathlib import Path
from typing import ClassVar

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition


class SureApp(App):
    name: ClassVar[str] = "sure"
    manifest_path: ClassVar[Path | None] = Path("sure.yaml")
    wait_target: ClassVar[str | None] = "deploy/sure"
    wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE
    wait_timeout: ClassVar[int] = 300


class SureStep(Step):
    name: ClassVar[str] = "Installing sure"
    app: App = SureApp()
    needs_secrets: ClassVar[bool] = True
