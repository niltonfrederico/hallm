"""Valkey (Redis-compatible) cache deployment."""

from pathlib import Path
from typing import ClassVar

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition
from hallm.core.settings import settings


class ValkeyApp(App):
    name: ClassVar[str] = "valkey"
    manifest_path: ClassVar[Path | None] = settings.K8S_PATH / "valkey.yaml"
    wait_target: ClassVar[str | None] = "deploy/valkey"
    wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE


class ValkeyStep(Step):
    name: ClassVar[str] = "Installing valkey"
    app: App = ValkeyApp()
    needs_secrets: ClassVar[bool] = True
