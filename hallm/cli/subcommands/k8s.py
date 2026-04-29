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
    """Sync .env → Secret 'hallm-env' and litellm/config.yaml → ConfigMap 'litellm-config'."""
    env_path = settings.ROOT_PATH / ".env"
    config_path = settings.ROOT_PATH / "litellm" / "config.yaml"

    if not env_path.exists():
        _fail(f".env not found at {env_path}")
    if not config_path.exists():
        _fail(f"litellm config not found at {config_path}")

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

    typer.echo("==> Syncing litellm/config.yaml → ConfigMap 'litellm-config'...")
    # Rewrite the Ollama base URL for in-cluster DNS before applying.
    k8s_config = config_path.read_text().replace(
        "http://ollama.hallm.local",
        "http://ollama.ollama.svc.cluster.local:11434",
    )
    apply = subprocess.run(
        [
            "kubectl",
            "create",
            "configmap",
            "litellm-config",
            "--from-literal",
            f"config.yaml={k8s_config}",
            "--dry-run=client",
            "-o",
            "yaml",
        ],
        text=True,
        capture_output=True,
    )
    if apply.returncode != 0:
        _fail(f"Failed to build ConfigMap 'litellm-config': {apply.stderr}")
    kubectl_apply = subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=apply.stdout,
        text=True,
        capture_output=True,
    )
    if kubectl_apply.returncode != 0:
        _fail(f"Failed to apply ConfigMap 'litellm-config': {kubectl_apply.stderr}")
    typer.echo("  ConfigMap 'litellm-config' applied.")

    typer.echo("==> Rolling out litellm deployment...")
    rollout = _run(["kubectl", "rollout", "restart", "deployment/litellm"])
    if rollout.returncode != 0:
        _fail(f"Rollout failed: {rollout.stderr}")
    typer.echo("  deployment/litellm restarted.")

    typer.echo("\nDone. Apply manifests with:")
    typer.echo("  kubectl apply -f k3d/postgres.yaml")
    typer.echo("  kubectl apply -f k3d/litellm.yaml")


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
