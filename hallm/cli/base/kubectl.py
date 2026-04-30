"""kubectl helper functions for CLI subcommands."""

import subprocess
from pathlib import Path

import typer

from hallm.cli.base.shell import fail
from hallm.cli.base.shell import run


def apply(manifest: str, *, label: str = "manifest") -> None:
    """Apply a Kubernetes manifest from a string piped to kubectl apply."""
    typer.echo(f"+ kubectl apply -f - [{label}]")
    result = subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=manifest,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        fail(f"kubectl apply {label} failed:\n{result.stderr}")


def apply_url(url: str) -> None:
    """Apply a Kubernetes manifest from a URL."""
    result = run(["kubectl", "apply", "-f", url])
    if result.returncode != 0:
        fail(f"kubectl apply failed:\n{result.stderr}")


def apply_from_cmd(label: str, source_cmd: list[str]) -> None:
    """Run source_cmd and pipe its stdout into kubectl apply."""
    src = subprocess.run(source_cmd, text=True, capture_output=True)
    if src.returncode != 0:
        fail(f"Failed to build {label}: {src.stderr}")
    apply(src.stdout, label=label)


def wait(
    resource: str,
    condition: str,
    *,
    namespace: str = "default",
    timeout: str = "60s",
) -> None:
    """Block until a resource satisfies the given condition."""
    result = run(
        [
            "kubectl",
            "wait",
            f"--for=condition={condition}",
            resource,
            "-n",
            namespace,
            f"--timeout={timeout}",
        ]
    )
    if result.returncode != 0:
        fail(f"{resource} did not reach condition={condition} within {timeout}.")


def rollout_restart(resource: str, *, namespace: str = "default") -> None:
    """Trigger a rollout restart for a deployment, statefulset, or daemonset."""
    result = run(["kubectl", "rollout", "restart", resource, "-n", namespace])
    if result.returncode != 0:
        fail(f"kubectl rollout restart {resource} failed:\n{result.stderr}")


def delete_manifest(manifest_path: str | Path, *, namespace: str = "default") -> None:
    """Delete all resources defined in a manifest file."""
    result = run(
        [
            "kubectl",
            "delete",
            "-f",
            str(manifest_path),
            "-n",
            namespace,
            "--ignore-not-found",
        ]
    )
    if result.returncode != 0:
        fail(f"Failed to delete resources from {manifest_path}: {result.stderr}")


def delete_by_label(kind: str, label: str, *, namespace: str = "default") -> None:
    """Delete all resources of a kind matching a label selector; warns on failure."""
    result = run(
        [
            "kubectl",
            "delete",
            kind,
            "-n",
            namespace,
            "-l",
            label,
            "--ignore-not-found",
        ]
    )
    if result.returncode != 0:
        typer.echo(f"  WARNING: failed to delete {kind}: {result.stderr}", err=True)
