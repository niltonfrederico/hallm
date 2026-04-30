"""k3d cluster management commands for the hallm local dev environment."""

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request

import typer

from hallm.cli.base import kubectl
from hallm.cli.base.shell import check as _check
from hallm.cli.base.shell import fail as _fail
from hallm.cli.base.shell import run as _run
from hallm.core.settings import settings

app = typer.Typer(help="k3d cluster operations.")

_CLUSTER_NAME = "hallm"
_DEVICE_PLUGIN_URL = (
    "https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml"
)
_CERT_MANAGER_URL = (
    "https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml"
)


def _manifest(*parts: str) -> str:
    return (settings.K3D_PATH / "/".join(parts)).read_text()


@app.command()
def setup() -> None:
    """Create the hallm k3d cluster, install the ROCm device plugin, and apply Cerberus PKI."""
    typer.echo("==> Creating k3d cluster...")
    result = _run(
        [
            "k3d",
            "cluster",
            "create",
            _CLUSTER_NAME,
            "--volume",
            "/dev/kfd:/dev/kfd@all",
            "--volume",
            "/dev/dri:/dev/dri@all",
            "-p",
            "80:80@loadbalancer",
            "-p",
            "443:443@loadbalancer",
        ]
    )
    if result.returncode != 0:
        _fail(f"k3d cluster create failed:\n{result.stderr}")

    typer.echo("\n==> Installing ROCm k8s device plugin...")
    kubectl.apply_url(_DEVICE_PLUGIN_URL)

    typer.echo("\n==> Installing cert-manager...")
    kubectl.apply_url(_CERT_MANAGER_URL)

    typer.echo("\n==> Waiting for cert-manager webhook to be ready...")
    kubectl.wait(
        "deploy/cert-manager-webhook",
        "Available",
        namespace="cert-manager",
        timeout="120s",
    )

    typer.echo("\n==> Applying Cerberus PKI (self-signed CA + ClusterIssuers)...")
    kubectl.apply(_manifest("cerberus.yaml"), label="Cerberus PKI")

    typer.echo("\n==> Done. Cluster is ready.")


@app.command()
def nuke(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete the hallm k3d cluster and all its resources."""
    if not yes:
        typer.confirm(
            f"This will permanently delete the '{_CLUSTER_NAME}' cluster. Continue?", abort=True
        )
    result = _run(["k3d", "cluster", "delete", _CLUSTER_NAME])
    if result.returncode != 0:
        _fail(f"k3d cluster delete failed:\n{result.stderr}")
    typer.echo(f"\nCluster '{_CLUSTER_NAME}' deleted.")


@app.command()
def healthcheck() -> None:
    """Verify the hallm cluster, GPU, Cerberus issuer, ports, and run smoke tests."""
    all_ok = True

    typer.echo("==> Static checks")

    # 1. Cluster running
    result = _run(["k3d", "cluster", "list", "-o", "json"])
    try:
        clusters: list[dict] = json.loads(result.stdout)
        cluster_ok = any(
            c.get("name") == _CLUSTER_NAME and c.get("serversRunning", 0) >= 1 for c in clusters
        )
    except json.JSONDecodeError, TypeError:
        cluster_ok = False
    all_ok &= _check(f"Cluster '{_CLUSTER_NAME}' is running", cluster_ok)

    # 2. GPU visible to Kubernetes
    result = _run(["kubectl", "get", "node", "-o", "json"])
    try:
        nodes: dict = json.loads(result.stdout)
        gpu_ok = any(
            int(item.get("status", {}).get("allocatable", {}).get("amd.com/gpu", "0")) >= 1
            for item in nodes.get("items", [])
        )
    except json.JSONDecodeError, ValueError, TypeError:
        gpu_ok = False
    all_ok &= _check("GPU (amd.com/gpu) visible to Kubernetes", gpu_ok)

    # 3. ROCm device plugin DaemonSet ready
    result = _run(["kubectl", "get", "ds", "-n", "kube-system", "-o", "json"])
    try:
        all_ds: dict = json.loads(result.stdout)
        amdgpu_ds = next(
            (
                item
                for item in all_ds.get("items", [])
                if "amdgpu" in item.get("metadata", {}).get("name", "")
            ),
            None,
        )
        if amdgpu_ds:
            ds_status = amdgpu_ds.get("status", {})
            desired = ds_status.get("desiredNumberScheduled", -1)
            ready = ds_status.get("numberReady", 0)
            ds_ok = desired >= 1 and desired == ready
        else:
            ds_ok = False
    except json.JSONDecodeError, TypeError:
        ds_ok = False
    all_ok &= _check("ROCm device plugin DaemonSet ready", ds_ok)

    # 4. Cerberus CA ClusterIssuer ready
    result = _run(["kubectl", "get", "clusterissuer", "cerberus-ca", "-o", "json"])
    try:
        issuer: dict = json.loads(result.stdout)
        conditions: list[dict] = issuer.get("status", {}).get("conditions", [])
        cerberus_ok = any(
            c.get("type") == "Ready" and c.get("status") == "True" for c in conditions
        )
    except json.JSONDecodeError, TypeError:
        cerberus_ok = False
    all_ok &= _check("Cerberus CA ClusterIssuer ready", cerberus_ok)

    # 5 & 6. Ports
    for port in (80, 443):
        try:
            with socket.create_connection(("localhost", port), timeout=3):
                port_ok = True
        except OSError:
            port_ok = False
        all_ok &= _check(f"Port {port} reachable on localhost", port_ok)

    typer.echo("\n==> GPU smoke test")
    all_ok &= _gpu_smoke_test()

    typer.echo("\n==> DNS smoke test")
    all_ok &= _dns_smoke_test()

    typer.echo()
    if all_ok:
        typer.echo("All checks passed.")
    else:
        typer.echo("One or more checks failed.", err=True)
        raise typer.Exit(code=1)


def _gpu_smoke_test() -> bool:
    """Deploy a GPU-requesting pod, wait for Succeeded, clean up. Return True on pass."""
    apply = subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=_manifest("test", "gpu-smoke.yaml"),
        text=True,
        capture_output=True,
    )
    if apply.returncode != 0:
        typer.echo(f"  [FAIL] Could not apply GPU smoke pod: {apply.stderr.strip()}", err=True)
        return False

    ok = False
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        phase = subprocess.run(
            ["kubectl", "get", "pod", "hallm-gpu-smoke", "-o", "jsonpath={.status.phase}"],
            text=True,
            capture_output=True,
        ).stdout.strip()
        if phase == "Succeeded":
            ok = True
            break
        if phase in ("Failed", "Unknown"):
            break
        time.sleep(2)

    _check("GPU smoke pod completed successfully", ok)

    subprocess.run(
        ["kubectl", "delete", "pod", "hallm-gpu-smoke", "--ignore-not-found"],
        capture_output=True,
    )
    return ok


def _dns_smoke_test() -> bool:
    """Deploy nginx + Ingress for test.hallm.local, verify HTTP, clean up. Return True on pass."""
    apply = subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=_manifest("test", "dns-smoke.yaml"),
        text=True,
        capture_output=True,
    )
    if apply.returncode != 0:
        typer.echo(
            f"  [FAIL] Could not apply DNS smoke resources: {apply.stderr.strip()}", err=True
        )
        _cleanup_dns_smoke()
        return False

    pod_ok = False
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "pods",
                "-l",
                "app=hallm-dns-smoke",
                "-o",
                "jsonpath={.items[0].status.phase}",
            ],
            text=True,
            capture_output=True,
        )
        if result.stdout.strip() == "Running":
            pod_ok = True
            break
        time.sleep(2)

    if not pod_ok:
        _check("DNS smoke pod running", False)
        _cleanup_dns_smoke()
        return False

    http_ok = False
    try:
        with urllib.request.urlopen("http://test.hallm.local", timeout=5) as resp:
            http_ok = resp.status < 400
    except urllib.error.HTTPError as exc:
        http_ok = exc.code < 400
    except OSError:
        http_ok = False

    _check("http://test.hallm.local reachable", http_ok)
    _cleanup_dns_smoke()
    return http_ok


def _cleanup_dns_smoke() -> None:
    subprocess.run(
        [
            "kubectl",
            "delete",
            "deploy/hallm-dns-smoke",
            "svc/hallm-dns-smoke",
            "ing/hallm-dns-smoke",
            "--ignore-not-found",
        ],
        capture_output=True,
    )
