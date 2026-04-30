"""Kubernetes operations for the hallm local dev environment."""

import subprocess

import typer

from hallm.cli.base import kubectl
from hallm.cli.base.shell import fail as _fail
from hallm.core.settings import settings

app = typer.Typer(help="Kubernetes operations.")

_DEFAULT_NAMESPACE = "default"


@app.command("sync-secrets")
def sync_secrets() -> None:
    """Sync .env → Secret 'hallm-env' in the cluster."""
    env_path = settings.ROOT_PATH / ".env"

    if not env_path.exists():
        _fail(f".env not found at {env_path}")

    typer.echo("==> Syncing .env → Secret 'hallm-env'...")
    kubectl.apply_from_cmd(
        "Secret 'hallm-env'",
        [
            "kubectl",
            "create",
            "secret",
            "generic",
            "hallm-env",
            f"--from-env-file={env_path}",
            "--dry-run=client",
            "-o",
            "yaml",
        ],
    )

    typer.echo("\nDone.")


@app.command()
def remove(
    name: str = typer.Argument(
        ..., help="Manifest name in k3d/ (without .yaml), e.g. 'ollama', 'postgres'"
    ),
    namespace: str = typer.Option(
        _DEFAULT_NAMESPACE, "--namespace", "-n", help="Kubernetes namespace"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Remove a deployment and all associated resources (volumes, secrets, configmaps, ingresses).

    Deletes everything defined in k3d/<name>.yaml, then sweeps for any PVCs, Secrets,
    and ConfigMaps labelled app=<name> in the target namespace.
    """
    manifest = settings.K3D_PATH / f"{name}.yaml"
    if not manifest.exists():
        _fail(
            f"No manifest found at {manifest}. "
            f"Available manifests: {', '.join(p.stem for p in settings.K3D_PATH.glob('*.yaml'))}"
        )

    # Collect the resource types to sweep by label after manifest deletion.
    _SWEEP_KINDS = ["persistentvolumeclaims", "secrets", "configmaps", "ingresses"]

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
    for kind in _SWEEP_KINDS:
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
        for kind in _SWEEP_KINDS:
            kubectl.delete_by_label(kind, f"app={name}", namespace=namespace)

    typer.echo(f"\nDone. '{name}' and associated resources removed.")
