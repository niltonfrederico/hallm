"""Shared host-backed ReadWriteMany volume for cross-pod data exchange."""

from pathlib import Path
from typing import ClassVar

from hallm.cli.base.poll import poll_until
from hallm.cli.base.shell import fail
from hallm.cli.base.shell import run
from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step


def _pvc_is_bound() -> bool:
    """Return True when the shared-volumes PVC reports ``status.phase=Bound``.

    PVCs do not expose ``Bound`` in ``.status.conditions``, so
    ``kubectl wait --for=condition=Bound`` always times out. Read the phase
    directly via ``-o jsonpath`` instead.
    """
    result = run(
        [
            "kubectl",
            "get",
            "pvc",
            "shared-volumes",
            "-n",
            "default",
            "-o",
            "jsonpath={.status.phase}",
        ]
    )
    return result.returncode == 0 and result.stdout.strip() == "Bound"


class SharedVolumesApp(App):
    name: ClassVar[str] = "shared-volumes"
    manifest_path: ClassVar[Path | None] = Path("shared-volumes.yaml")


class SharedVolumesStep(Step):
    name: ClassVar[str] = "Installing shared-volumes PV/PVC"
    app: App = SharedVolumesApp()

    def is_satisfied(self) -> bool:
        return _pvc_is_bound()

    def post_validate(self) -> None:
        if not poll_until(_pvc_is_bound, timeout=60.0, interval=2.0):
            fail("pvc/shared-volumes did not reach phase=Bound within 60s.")
