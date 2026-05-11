"""Synthetic Step: idempotently create every namespace the pipeline declares."""

from typing import ClassVar

import typer

from hallm.cli.base.shell import run as _run
from hallm.cli.subcommands.cluster.setup_builders.base import Step


class BootstrapNamespacesStep(Step):
    """Create every namespace needed by the pipeline. Inserted by the builder
    right after the is_cluster_ready_marker; never authored manually."""

    name: ClassVar[str] = "Bootstrapping namespaces"

    def __init__(self, namespaces: frozenset[str]) -> None:
        self._namespaces = sorted(namespaces)

    @property
    def required_namespaces(self) -> frozenset[str]:
        # Bootstrap step itself provides the namespaces; nothing required of it.
        return frozenset()

    def run(self) -> None:
        for ns in self._namespaces:
            typer.echo(f"  ensuring namespace/{ns}")
            # `kubectl create namespace` is idempotent enough for our purposes:
            # AlreadyExists is silenced; any other failure surfaces.
            result = _run(["kubectl", "create", "namespace", ns])
            if result.returncode != 0 and "AlreadyExists" not in result.stderr:
                raise RuntimeError(f"failed to create namespace {ns}: {result.stderr.strip()}")
