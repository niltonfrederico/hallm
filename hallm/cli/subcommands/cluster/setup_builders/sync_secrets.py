"""Synthetic Step: sync ~/.hallm/*.env into Kubernetes Secrets.

Auto-inserted by the builder before the first Step with needs_secrets=True.
Delegates to secrets._sync_secrets so the on-disk convention stays in one place.
"""

from typing import ClassVar

from hallm.cli.subcommands import secrets as _secrets
from hallm.cli.subcommands.cluster.setup_builders.base import Step


class SyncSecretsStep(Step):
    name: ClassVar[str] = "Syncing secrets"

    def run(self) -> None:
        _secrets._sync_secrets()
