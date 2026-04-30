"""Kubernetes operations for the hallm local dev environment."""

import subprocess
import time

import typer

from hallm.core.settings import settings

app = typer.Typer(help="Kubernetes operations.")

_DEFAULT_NAMESPACE = "default"


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    typer.echo(f"+ {' '.join(cmd)}")
    return subprocess.run(cmd, text=True, capture_output=True)


def _fail(message: str) -> None:
    typer.echo(f"ERROR: {message}", err=True)
    raise typer.Exit(code=1)


def _kubectl_apply_from_stdout(label: str, source_cmd: list[str]) -> None:
    result = subprocess.run(source_cmd, text=True, capture_output=True)
    if result.returncode != 0:
        _fail(f"Failed to build {label}: {result.stderr}")
    apply = subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=result.stdout,
        text=True,
        capture_output=True,
    )
    if apply.returncode != 0:
        _fail(f"Failed to apply {label}: {apply.stderr}")
    typer.echo(f"  {label} applied.")


@app.command("sync-secrets")
def sync_secrets() -> None:
    """Sync .env → Secret 'hallm-env' in the cluster."""
    env_path = settings.ROOT_PATH / ".env"

    if not env_path.exists():
        _fail(f".env not found at {env_path}")

    typer.echo("==> Syncing .env → Secret 'hallm-env'...")
    _kubectl_apply_from_stdout(
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
    result = _run(["kubectl", "delete", "-f", str(manifest), "-n", namespace, "--ignore-not-found"])
    if result.returncode != 0:
        _fail(f"Failed to delete manifest resources: {result.stderr}")

    if label_resources:
        typer.echo(f"==> Sweeping labelled resources (app={name})...")
        for kind in _SWEEP_KINDS:
            result = _run(
                [
                    "kubectl",
                    "delete",
                    kind,
                    "-n",
                    namespace,
                    "-l",
                    f"app={name}",
                    "--ignore-not-found",
                ]
            )
            if result.returncode != 0:
                typer.echo(f"  WARNING: failed to delete {kind}: {result.stderr}", err=True)

    typer.echo(f"\nDone. '{name}' and associated resources removed.")


@app.command()
def job(
    name: str = typer.Argument(..., help="Job name (matches filename in k3d/jobs/ without .yaml)"),
    namespace: str = typer.Option(
        _DEFAULT_NAMESPACE, "--namespace", "-n", help="Kubernetes namespace"
    ),
    timeout: int = typer.Option(300, "--timeout", "-t", help="Max seconds to wait for completion"),
) -> None:
    """Delete any prior run, apply k3d/jobs/<name>.yaml, and stream its logs."""
    manifest = settings.K3D_PATH / "jobs" / f"{name}.yaml"
    if not manifest.exists():
        _fail(f"Job manifest not found: {manifest}")

    typer.echo(f"==> Cleaning up any prior run of job '{name}'...")
    subprocess.run(
        ["kubectl", "delete", "job", name, "-n", namespace, "--ignore-not-found"],
        capture_output=True,
    )

    typer.echo(f"==> Applying job '{name}'...")
    result = _run(["kubectl", "apply", "-f", str(manifest)])
    if result.returncode != 0:
        _fail(f"Failed to apply job: {result.stderr}")

    typer.echo("==> Waiting for pod to start...")
    pod_name = ""
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "pods",
                "-n",
                namespace,
                "-l",
                f"job-name={name}",
                "-o",
                "jsonpath={.items[0].metadata.name}",
            ],
            text=True,
            capture_output=True,
        )
        pod_name = result.stdout.strip()
        if pod_name:
            break
        time.sleep(2)

    if not pod_name:
        _fail("Pod did not appear within 60 seconds.")

    # Wait for the pod to leave Pending
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["kubectl", "get", "pod", pod_name, "-n", namespace, "-o", "jsonpath={.status.phase}"],
            text=True,
            capture_output=True,
        )
        if result.stdout.strip() not in ("", "Pending"):
            break
        time.sleep(2)

    typer.echo(f"==> Streaming logs from {pod_name}...\n")
    subprocess.run(["kubectl", "logs", "-f", pod_name, "-n", namespace])

    typer.echo(f"\n==> Checking final status of job '{name}'...")
    wait_result = subprocess.run(
        [
            "kubectl",
            "wait",
            f"job/{name}",
            "--for=condition=complete",
            f"--timeout={timeout}s",
            "-n",
            namespace,
        ],
        text=True,
        capture_output=True,
    )
    if wait_result.returncode == 0:
        typer.echo(f"Job '{name}' completed successfully.")
    else:
        failed = subprocess.run(
            [
                "kubectl",
                "wait",
                f"job/{name}",
                "--for=condition=failed",
                "--timeout=5s",
                "-n",
                namespace,
            ],
            text=True,
            capture_output=True,
        )
        if failed.returncode == 0:
            _fail(f"Job '{name}' failed.")
        else:
            _fail(f"Job '{name}' did not complete within {timeout}s.")
