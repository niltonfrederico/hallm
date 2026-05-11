"""Shared image build+push helper for the hallm unregistry.

Both the ``hallm container publish`` subcommand and cluster setup steps that
need a custom image (e.g. Jupyter) route through :func:`build_and_push` so the
buildx flags and tag convention live in exactly one place.
"""

from datetime import UTC
from datetime import datetime
from pathlib import Path

import typer

from hallm.cli.base import docker as _docker

REGISTRY = "unregistry.hallm.local"
ORG = "hallm"


def build_and_push(dockerfile: Path, image_name: str, context: Path) -> None:
    """Build `dockerfile` and push as <REGISTRY>/<ORG>/<image_name>:{latest,<ts>}.

    ``--output type=registry`` builds and pushes in one shot without populating
    the local image store. ``--provenance=false --sbom=false`` and an explicit
    ``--platform`` keep the result a plain ``application/vnd.docker.distribution.
    manifest.v2+json`` rather than an OCI image index — unregistry's containerd
    backend resolves the former cleanly but loses the tag binding for the
    latter, which surfaces as ``ErrImagePull: not found`` on the pulling node.
    """
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
    base_tag = f"{REGISTRY}/{ORG}/{image_name}"
    tag_latest = f"{base_tag}:latest"
    tag_ts = f"{base_tag}:{timestamp}"

    typer.echo(f"==> Building and pushing {image_name} from {dockerfile.name}...")
    _docker.run_or_fail(
        [
            "docker",
            "buildx",
            "build",
            "--platform",
            "linux/amd64",
            "--provenance=false",
            "--sbom=false",
            "--tag",
            tag_latest,
            "--tag",
            tag_ts,
            "--file",
            str(dockerfile),
            "--output",
            "type=registry",
            str(context),
        ],
        f"Build/push failed for {image_name}",
        stream=True,
    )

    typer.echo(f"\n[OK]  {image_name} published as {tag_latest} and {tag_ts}")
