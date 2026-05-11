"""Poll the Kubernetes API until kubectl can reach it.

is_cluster_ready_marker=True signals the builder to insert
BootstrapNamespacesStep right after this Step.
"""

from typing import ClassVar

from hallm.cli.base.poll import poll_until
from hallm.cli.base.shell import fail as _fail
from hallm.cli.base.shell import run as _run
from hallm.cli.subcommands.cluster.setup_builders.base import Step


class WaitApiStep(Step):
    name: ClassVar[str] = "Waiting for Kubernetes API server"
    is_cluster_ready_marker: ClassVar[bool] = True

    def run(self) -> None:
        ready = poll_until(
            lambda: _run(["kubectl", "get", "nodes"]).returncode == 0,
            timeout=120,
            interval=3.0,
        )
        if not ready:
            _fail("Kubernetes API server did not become ready in time")
