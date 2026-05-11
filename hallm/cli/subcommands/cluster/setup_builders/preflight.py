"""Step wrapper around the cluster preflight checks."""

from typing import ClassVar

from hallm.cli.subcommands.cluster.preflight import _run_preflight
from hallm.cli.subcommands.cluster.setup_builders.base import Step


class PreflightStep(Step):
    name: ClassVar[str] = "Running preflight checks"

    def run(self) -> None:
        _run_preflight()
