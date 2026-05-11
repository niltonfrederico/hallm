"""memory-mcp deployment."""

from pathlib import Path
from typing import ClassVar

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition


class MemoryMcpApp(App):
    name: ClassVar[str] = "memory-mcp"
    manifest_path: ClassVar[Path | None] = Path("memory-mcp.yaml")
    wait_target: ClassVar[str | None] = "deploy/memory-mcp"
    wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE


class MemoryMcpStep(Step):
    name: ClassVar[str] = "Installing memory-mcp"
    app: App = MemoryMcpApp()
