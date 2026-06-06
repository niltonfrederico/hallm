"""Stop or start a family of Deployments by scaling the `app=<family>` label.

A "family" is everything sharing an ``app:`` label — every immich component,
every paperless component, etc. Stopping scales the matching Deployments to
zero, freeing pod resources (RAM, GPU) while preserving PersistentVolumeClaims,
Services, Ingresses, and Secrets. Starting scales back to one replica.

Multi-replica Deployments are not yet supported — every Deployment in this
repo is ``replicas: 1``, and ``start`` assumes that. When the first
multi-replica workload lands, stash the original count in a
``hallm.io/original-replicas`` annotation during stop and read it back on
start.
"""

import typer

from hallm.cli.base import kubectl


def stop(
    family: str = typer.Argument(
        ...,
        help="Value of the app= label (e.g. 'immich', 'paperless').",
    ),
    namespace: str = typer.Option(
        "default",
        "--namespace",
        "-n",
        help="Kubernetes namespace to scope the selector to.",
    ),
) -> None:
    """Scale every Deployment with ``app=<family>`` down to zero replicas."""
    names = kubectl.scale_by_label(f"app={family}", 0, namespace=namespace)
    typer.echo(f"Stopped {len(names)} deployment(s) in family '{family}': {', '.join(names)}")


def start(
    family: str = typer.Argument(
        ...,
        help="Value of the app= label (e.g. 'immich', 'paperless').",
    ),
    namespace: str = typer.Option(
        "default",
        "--namespace",
        "-n",
        help="Kubernetes namespace to scope the selector to.",
    ),
) -> None:
    """Scale every Deployment with ``app=<family>`` back up to one replica."""
    names = kubectl.scale_by_label(f"app={family}", 1, namespace=namespace)
    typer.echo(f"Started {len(names)} deployment(s) in family '{family}': {', '.join(names)}")
