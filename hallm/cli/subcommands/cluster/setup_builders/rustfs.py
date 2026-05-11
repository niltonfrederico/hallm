"""RustFS (S3-compatible object storage) deployment."""

from pathlib import Path
from typing import ClassVar

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition


class RustfsApp(App):
    name: ClassVar[str] = "rustfs"
    manifest_path: ClassVar[Path | None] = Path("rustfs.yaml")
    wait_target: ClassVar[str | None] = "deploy/rustfs"
    wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE


class RustfsStep(Step):
    name: ClassVar[str] = "Installing rustfs"
    app: App = RustfsApp()
    needs_secrets: ClassVar[bool] = True
