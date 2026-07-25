"""Container image build, push, deploy, and removal operations."""

import subprocess
from pathlib import Path

import typer

from hallm.cli.base import kubectl
from hallm.cli.base.container import build_and_push
from hallm.cli.base.shell import fail as _fail
from hallm.core import workspace
from hallm.core.settings import settings

app = typer.Typer(help="Container image operations.", no_args_is_help=True)

_DEFAULT_NAMESPACE = "default"


def _publish(name: str) -> None:
    """Resolve <name> to docker/Dockerfile.<name> and publish."""
    dockerfile = settings.docker_path / f"Dockerfile.{name}"
    if not dockerfile.exists():
        _fail(f"Dockerfile not found: {dockerfile}")
    build_and_push(dockerfile, name, context=settings.repo_root)


@app.command("publish")
def publish(
    target: str = typer.Argument(
        ...,
        help=("Service name (resolved to docker/Dockerfile.<name>) or a path to a Dockerfile."),
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        "-n",
        help=(
            "Image name override. Required when target is a Dockerfile path "
            "whose filename is not Dockerfile.<name>."
        ),
    ),
) -> None:
    """Build and push an image to unregistry.

    Two forms:
      - `publish <name>` — builds docker/Dockerfile.<name> with the repo root
        as build context.
      - `publish <path>` — builds the given Dockerfile with its parent
        directory as build context. The image name is derived from
        `Dockerfile.<name>` filenames; pass `--name` otherwise.
    """
    candidate = Path(target)
    if candidate.is_file():
        dockerfile = candidate.resolve()
        image_name = name
        if image_name is None:
            if dockerfile.name.startswith("Dockerfile."):
                image_name = dockerfile.name.removeprefix("Dockerfile.")
            else:
                _fail(f"Cannot derive image name from {dockerfile.name}; pass --name.")
        build_and_push(dockerfile, image_name, context=dockerfile.parent)
        return

    if name is not None:
        _fail("--name is only valid when target is a Dockerfile path.")
    _publish(target)


def _resolve_manifest_target(target: str) -> tuple[Path, str]:
    """Resolve `target` to (manifest path, label name).

    Two forms:
      - bare name → ``$repo/k8s/<name>.yaml`` (label = name)
      - file path → manifest at that path (label = filename stem)
    """
    candidate = Path(target)
    if candidate.is_file():
        return candidate.resolve(), candidate.stem
    manifest = settings.k8s_path / f"{target}.yaml"
    if not manifest.exists():
        _fail(
            f"No manifest found at {manifest}. "
            f"Available: {', '.join(p.stem for p in settings.k8s_path.glob('*.yaml'))}"
        )
    return manifest, target


@app.command()
def deploy(
    target: str = typer.Argument(
        ...,
        help=(
            "Service name (resolved to k8s/<name>.yaml) or a path to a manifest file. "
            "Auto-build only fires for the name form."
        ),
    ),
    build: bool = typer.Option(
        True, "--build/--no-build", help="Build and push image before applying."
    ),
    restart: bool | None = typer.Option(
        None,
        "--restart/--no-restart",
        help=(
            "Roll out the pods after applying. Defaults to restarting only when "
            "a new image was built."
        ),
    ),
    namespace: str = typer.Option(
        _DEFAULT_NAMESPACE, "--namespace", "-n", help="Kubernetes namespace."
    ),
) -> None:
    """Apply k8s/<name>.yaml (or an arbitrary manifest), optionally building first.

    If a docker/Dockerfile.<name> exists and --build is set (the default), the
    image is built and pushed to unregistry before the manifest is applied.
    Pass --no-build to skip the build step (e.g. when re-deploying an image
    that is already in the registry, or when target is a manifest path).

    A build is followed by a rollout restart of the Deployments labelled
    app=<name>. `kubectl apply` is declarative, so an unchanged manifest is a
    no-op -- and because every image is pinned to the fixed `:latest` tag, the
    manifest does *not* change when the image does. Without the restart the new
    image sits in the registry while the old pods keep serving. Use --restart to
    force one without rebuilding, or --no-restart to suppress it.
    """
    candidate = Path(target)
    is_path = candidate.is_file()
    manifest, label = _resolve_manifest_target(target)

    built = False
    if build and not is_path:
        dockerfile = settings.docker_path / f"Dockerfile.{target}"
        if dockerfile.exists():
            _publish(target)
            built = True

    kubectl.apply(manifest.read_text(), label=label)

    if built if restart is None else restart:
        restarted = kubectl.rollout_restart_by_label(f"app={label}", namespace=namespace)
        if restarted:
            for name in restarted:
                typer.echo(f"+ kubectl rollout restart deploy/{name} [{namespace}]")
        else:
            typer.echo(f"  (no Deployment labelled app={label} in namespace '{namespace}')")

    typer.echo(f"\n[OK]  {label} deployed.")


@app.command()
def remove(
    target: str = typer.Argument(
        ...,
        help=("Manifest name in k8s/ (without .yaml) or a path to a manifest file."),
    ),
    namespace: str = typer.Option(
        _DEFAULT_NAMESPACE, "--namespace", "-n", help="Kubernetes namespace."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Remove a deployment and all associated resources (volumes, secrets, configmaps, ingresses).

    Deletes everything defined in the resolved manifest, then sweeps for any PVCs,
    Secrets, and ConfigMaps labelled app=<name> in the target namespace.
    """
    manifest, name = _resolve_manifest_target(target)
    sweep_kinds = ["persistentvolumeclaims", "secrets", "configmaps", "ingresses"]

    repo = workspace.find_repo()
    if repo is not None:
        try:
            location = str(manifest.relative_to(repo))
        except ValueError:
            location = str(manifest)
    else:
        location = str(manifest)
    typer.echo(f"==> Resources to remove (from {location}):")
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
