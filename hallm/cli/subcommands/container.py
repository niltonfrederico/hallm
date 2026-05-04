"""Container image build, push, deploy, and removal operations."""

import subprocess
from datetime import UTC
from datetime import datetime

import typer

from hallm.cli.base import docker as _docker
from hallm.cli.base import kubectl
from hallm.cli.base.shell import fail as _fail
from hallm.core.settings import settings

app = typer.Typer(help="Container image operations.", no_args_is_help=True)

_REGISTRY = "unregistry.hallm.local"
_ORG = "hallm"
_DEFAULT_NAMESPACE = "default"


def _publish(name: str) -> None:
    """Build, tag (latest + timestamp), and push <name> to unregistry."""
    dockerfile = settings.ROOT_PATH / "docker" / f"Dockerfile.{name}"
    if not dockerfile.exists():
        _fail(f"Dockerfile not found: {dockerfile}")

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
    base_tag = f"{_REGISTRY}/{_ORG}/{name}"
    tag_latest = f"{base_tag}:latest"
    tag_ts = f"{base_tag}:{timestamp}"

    typer.echo(f"==> Building {name} from {dockerfile.name}...")
    _docker.run_or_fail(
        [
            "docker",
            "build",
            "--tag",
            tag_latest,
            "--tag",
            tag_ts,
            "--file",
            str(dockerfile),
            str(settings.ROOT_PATH),
        ],
        f"Build failed for {name}",
        stream=True,
    )

    for tag in (tag_latest, tag_ts):
        typer.echo(f"==> Pushing {tag}...")
        _docker.run_or_fail(["docker", "push", tag], f"Push failed for {tag}")

    typer.echo("==> Pruning local Docker build cache...")
    result = _docker.run(["docker", "buildx", "prune", "--force"])
    if result.returncode != 0:
        typer.echo(f"WARNING: cache prune failed: {result.stderr}", err=True)
    else:
        typer.echo(result.stdout.strip() or "  Cache cleared.")

    typer.echo(f"\n[OK]  {name} published as {tag_latest} and {tag_ts}")


@app.command("publish")
def publish(
    name: str = typer.Argument(..., help="Image name to build and push (e.g. activitywatch)."),
) -> None:
    """Build, tag (latest + timestamp), push to unregistry, and prune local cache."""
    _publish(name)


@app.command()
def deploy(
    name: str = typer.Argument(
        ..., help="Service name — matches k8s/<name>.yaml and docker/Dockerfile.<name>."
    ),
    build: bool = typer.Option(
        True, "--build/--no-build", help="Build and push image before applying."
    ),
) -> None:
    """Apply k8s/<name>.yaml, optionally building and pushing the image first.

    If a docker/Dockerfile.<name> exists and --build is set (the default), the
    image is built and pushed to unregistry before the manifest is applied.
    Pass --no-build to skip the build step (e.g. when re-deploying an image
    that is already in the registry).
    """
    manifest = settings.K8S_PATH / f"{name}.yaml"
    if not manifest.exists():
        _fail(
            f"No manifest found at {manifest}. "
            f"Available: {', '.join(p.stem for p in settings.K8S_PATH.glob('*.yaml'))}"
        )

    dockerfile = settings.ROOT_PATH / "docker" / f"Dockerfile.{name}"
    if build and dockerfile.exists():
        _publish(name)

    kubectl.apply(manifest.read_text(), label=name)
    typer.echo(f"\n[OK]  {name} deployed.")


@app.command()
def remove(
    name: str = typer.Argument(
        ..., help="Manifest name in k8s/ (without .yaml), e.g. 'postgres', 'valkey'."
    ),
    namespace: str = typer.Option(
        _DEFAULT_NAMESPACE, "--namespace", "-n", help="Kubernetes namespace."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Remove a deployment and all associated resources (volumes, secrets, configmaps, ingresses).

    Deletes everything defined in k8s/<name>.yaml, then sweeps for any PVCs, Secrets,
    and ConfigMaps labelled app=<name> in the target namespace.
    """
    manifest = settings.K8S_PATH / f"{name}.yaml"
    if not manifest.exists():
        _fail(
            f"No manifest found at {manifest}. "
            f"Available manifests: {', '.join(p.stem for p in settings.K8S_PATH.glob('*.yaml'))}"
        )

    sweep_kinds = ["persistentvolumeclaims", "secrets", "configmaps", "ingresses"]

    typer.echo(f"==> Resources to remove (from {manifest.relative_to(settings.ROOT_PATH)}):")
    preview = subprocess.run(
        ["kubectl", "get", "-f", str(manifest), "-n", namespace, "--ignore-not-found"],
        text=True,
        capture_output=True,
    )
    if preview.stdout.strip():
        for line in preview.stdout.strip().splitlines():
            typer.echo(f"  {line}")
    else:
        typer.echo("  (no manifest resources currently exist in the cluster)")

    label_resources: list[str] = []
    for kind in sweep_kinds:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                kind,
                "-n",
                namespace,
                "-l",
                f"app={name}",
                "--ignore-not-found",
                "-o",
                "name",
            ],
            text=True,
            capture_output=True,
        )
        for line in result.stdout.strip().splitlines():
            if line:
                label_resources.append(line)

    if label_resources:
        typer.echo(f"\n==> Additional resources labelled app={name}:")
        for r in label_resources:
            typer.echo(f"  {r}")

    if not yes:
        typer.confirm(f"\nDelete all of the above in namespace '{namespace}'?", abort=True)

    typer.echo(f"\n==> Deleting manifest resources from {manifest.name}...")
    kubectl.delete_manifest(manifest, namespace=namespace)

    if label_resources:
        typer.echo(f"==> Sweeping labelled resources (app={name})...")
        for kind in sweep_kinds:
            kubectl.delete_by_label(kind, f"app={name}", namespace=namespace)

    typer.echo(f"\nDone. '{name}' and associated resources removed.")
