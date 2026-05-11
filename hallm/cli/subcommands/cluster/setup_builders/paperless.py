"""Paperless-ngx document management (web + tika + gotenberg)."""

from pathlib import Path
from typing import ClassVar

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition
from hallm.core.settings import settings


class PaperlessApp(App):
    name: ClassVar[str] = "paperless"
    manifest_path: ClassVar[Path | None] = settings.K8S_PATH / "paperless.yaml"
    wait_target: ClassVar[str | None] = "deploy/paperless"
    wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE
    wait_timeout: ClassVar[int] = 300


class PaperlessStep(Step):
    name: ClassVar[str] = "Installing paperless"
    app: App = PaperlessApp()
    needs_secrets: ClassVar[bool] = True
