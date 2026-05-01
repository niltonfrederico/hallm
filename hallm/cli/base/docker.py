"""Docker context routing helpers.

The hallm k3d cluster runs on a dedicated rootless Docker daemon, exposed via
the Docker context named in :attr:`Settings.DOCKER_CONTEXT`. Every ``k3d`` and
``docker`` invocation from the CLI must target that context so the user's
default Docker daemon stays untouched.

Both the Docker CLI and ``k3d`` honor the ``DOCKER_CONTEXT`` env var via the
Docker Go SDK, so a single env-var injection at the subprocess boundary is
enough — no daemon socket plumbing required.
"""

import subprocess

from hallm.cli.base import shell
from hallm.core.settings import settings


def context_env() -> dict[str, str]:
    """Return the env override that pins subprocesses to the hallm Docker context."""
    return {"DOCKER_CONTEXT": settings.DOCKER_CONTEXT}


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command pinned to the hallm Docker context."""
    return shell.run(cmd, env=context_env())


def run_or_fail(cmd: list[str], error_msg: str) -> subprocess.CompletedProcess[str]:
    """Run a command pinned to the hallm Docker context; fail on non-zero exit."""
    return shell.run_or_fail(cmd, error_msg, env=context_env())
