"""Abstract building blocks for the cluster setup pipeline.

Steps are the unit of execution; each has a lifecycle of pre_validate → pre →
run → post_validate → post. Apps are declarative descriptions of installable
components (manifest + namespace + readiness target) attached optionally to a
Step. build_setup_pipeline composes an ordered list of Steps into a runnable
callable, auto-inserting three synthetic phases:

  A — namespaces: every Step.required_namespaces is unioned with
      ClusterSettings.REQUIRED_NAMESPACES and a BootstrapNamespacesStep is
      inserted right after the is_cluster_ready_marker.
  B — manifest claim validation: Apps with manifest_path "claim" files in
      k8s/. Any k8s/*.yaml left unclaimed (other than registries.yaml)
      raises SetupStepError at build time — discipline gate that forces new
      yaml to register an App.
  D — secrets sync: the first Step with needs_secrets=True triggers a
      SyncSecretsStep inserted right before it (once).

Failure during run() is wrapped in SetupStepError; the pipeline runs
`k3d cluster delete <NAME>` before re-raising (global nuke rollback).
"""

from abc import ABCMeta
from collections.abc import Callable
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

import typer

from hallm.cli.base import docker as _docker
from hallm.cli.base import kubectl
from hallm.core.settings import ClusterSettings
from hallm.core.settings import settings


class WaitCondition(StrEnum):
    """kubectl wait --for=condition=<X> values used across cluster Apps."""

    AVAILABLE = "Available"
    READY = "Ready"
    COMPLETE = "complete"


class SetupStepError(Exception):
    """Raised when any phase of a Step fails or when the builder rejects the plan."""

    def __init__(self, message: str, *, step_name: str | None = None) -> None:
        super().__init__(message)
        self.step_name = step_name


class App(metaclass=ABCMeta):
    """Declarative description of an installable cluster component.

    Subclasses set class attributes (name, namespace, manifest_path or
    manifest_url, optional wait_target). install()/wait() have sensible
    defaults driven by those attributes; override only when the install path
    is non-standard (helm, restore-from-files, etc.).
    """

    name: ClassVar[str]
    namespace: ClassVar[str] = ClusterSettings.DEFAULT_NAMESPACE

    # Manifest source — pick exactly one (or override install()).
    manifest_path: ClassVar[Path | None] = None
    manifest_url: ClassVar[str | None] = None

    # Readiness check (skipped when wait_target is None).
    wait_target: ClassVar[str | None] = None
    wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE
    wait_timeout: ClassVar[int] = 180

    def install(self) -> None:
        if self.manifest_path is not None:
            kubectl.apply(self.manifest_path.read_text(), label=self.name)
            return
        if self.manifest_url is not None:
            kubectl.apply_url(self.manifest_url)
            return
        raise NotImplementedError(
            f"App '{self.name}' has no manifest_path/manifest_url and does not override install()."
        )

    def wait(self) -> None:
        if self.wait_target is None:
            return
        kubectl.wait(
            self.wait_target,
            self.wait_condition.value,
            namespace=self.namespace,
            timeout=f"{self.wait_timeout}s",
        )


class Step(metaclass=ABCMeta):
    """A single ordered action in the setup pipeline."""

    name: ClassVar[str]
    app: App | None = None

    # Builder synthesis hooks.
    is_cluster_ready_marker: ClassVar[bool] = False
    needs_secrets: ClassVar[bool] = False

    @property
    def required_namespaces(self) -> frozenset[str]:
        return frozenset({self.app.namespace}) if self.app is not None else frozenset()

    def pre_validate(self) -> None:
        return None

    def pre(self) -> None:
        return None

    def run(self) -> None:
        if self.app is not None:
            self.app.install()
            return
        raise NotImplementedError(f"Step '{self.name}' has no app and does not override run().")

    def post(self) -> None:
        return None

    def post_validate(self) -> None:
        if self.app is not None:
            self.app.wait()


def _validate_manifest_claims(steps: Sequence[Step]) -> None:
    claimed: set[Path] = {
        s.app.manifest_path for s in steps if s.app is not None and s.app.manifest_path is not None
    }
    all_manifests: set[Path] = set(settings.K8S_PATH.glob("*.yaml"))
    unclaimed = sorted(all_manifests - claimed - {settings.K8S_PATH / "registries.yaml"})
    if unclaimed:
        names = sorted(p.name for p in unclaimed)
        raise SetupStepError(
            f"manifests in k8s/ without a registered App: {names} — "
            f"create an App for each, or move them to k8s/archived/."
        )


def _collect_namespaces(steps: Sequence[Step]) -> frozenset[str]:
    declared: frozenset[str] = frozenset().union(*(s.required_namespaces for s in steps))
    return declared | frozenset(ClusterSettings.REQUIRED_NAMESPACES)


def build_setup_pipeline(steps: Sequence[Step]) -> Callable[[], None]:
    """Compose an ordered list of Steps into a runnable callable.

    User order is preserved; the builder only INSERTS synthetic Steps.
    """
    # Local imports avoid a circular dependency: those modules import App/Step from here.
    from hallm.cli.subcommands.cluster.setup_builders.bootstrap_namespaces import (
        BootstrapNamespacesStep,
    )
    from hallm.cli.subcommands.cluster.setup_builders.sync_secrets import SyncSecretsStep

    _validate_manifest_claims(steps)
    namespaces = _collect_namespaces(steps)

    plan: list[Step] = []
    secrets_inserted = False
    for step in steps:
        if step.needs_secrets and not secrets_inserted:
            plan.append(SyncSecretsStep())
            secrets_inserted = True
        plan.append(step)
        if step.is_cluster_ready_marker:
            plan.append(BootstrapNamespacesStep(namespaces))

    def run() -> None:
        for step in plan:
            typer.echo(f"\n==> {step.name}...")
            try:
                step.pre_validate()
                step.pre()
                step.run()
                step.post_validate()
                step.post()
            except Exception as exc:
                typer.echo(f"\n==> Nuking cluster after failure in '{step.name}'...")
                _docker.run(["k3d", "cluster", "delete", ClusterSettings.NAME])
                raise SetupStepError(
                    f"Setup step '{step.name}' failed", step_name=step.name
                ) from exc

    return run
