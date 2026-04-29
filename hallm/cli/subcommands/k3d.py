"""k3d cluster management commands for the hallm local dev environment."""

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request

import typer

from hallm.core.settings import settings

app = typer.Typer(help="k3d cluster operations.")

_CLUSTER_NAME = "hallm"
_DEVICE_PLUGIN_URL = (
    "https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml"
)
_CERT_MANAGER_URL = (
    "https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml"
)

_GPU_SMOKE_MANIFEST = (settings.K3D_PATH / "test" / "gpu-smoke.yaml").read_text()
_DNS_SMOKE_MANIFEST = (settings.K3D_PATH / "test" / "dns-smoke.yaml").read_text()
_CERBERUS_MANIFEST = (settings.K3D_PATH / "cerberus.yaml").read_text()


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    typer.echo(f"+ {' '.join(cmd)}")
    return subprocess.run(cmd, text=True, capture_output=True)


def _fail(message: str) -> None:
    typer.echo(f"ERROR: {message}", err=True)
    raise typer.Exit(code=1)


def _check(label: str, ok: bool) -> bool:
    status = "[OK]  " if ok else "[FAIL]"
    typer.echo(f"  {status} {label}")
    return ok


@app.command()
def setup() -> None:
    """Create the hallm k3d cluster, install the ROCm device plugin, and create the ollama namespace."""
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
    result = _run(["kubectl", "apply", "-f", _DEVICE_PLUGIN_URL])
    if result.returncode != 0:
        _fail(f"kubectl apply device plugin failed:\n{result.stderr}")

    typer.echo("\n==> Installing cert-manager...")
    result = _run(["kubectl", "apply", "-f", _CERT_MANAGER_URL])
    if result.returncode != 0:
        _fail(f"kubectl apply cert-manager failed:\n{result.stderr}")

    typer.echo("\n==> Waiting for cert-manager webhook to be ready...")
    result = _run(
        [
            "kubectl",
            "wait",
            "--for=condition=Available",
            "deploy/cert-manager-webhook",
            "-n",
            "cert-manager",
            "--timeout=120s",
        ]
    )
    if result.returncode != 0:
        _fail("cert-manager webhook did not become ready in time.")

    typer.echo("\n==> Applying Cerberus PKI (self-signed CA + ClusterIssuers)...")
    result = subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=_CERBERUS_MANIFEST,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        _fail(f"kubectl apply cerberus failed:\n{result.stderr}")

    typer.echo("\n==> Creating ollama namespace...")
    result = _run(["kubectl", "create", "namespace", "ollama"])
    if result.returncode != 0:
        _fail(f"kubectl create namespace failed:\n{result.stderr}")

    typer.echo("\n==> Done. Cluster is ready.\n")
    typer.echo(
        "REMINDER: Any deployment that uses the GPU must set:\n"
        "  env:\n"
        "    - name: HSA_OVERRIDE_GFX_VERSION\n"
        '      value: "10.3.0"'
    )


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
    """Verify the hallm cluster, GPU, namespaces, ports, and run hello-world smoke tests."""
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

    # 3. ROCm device plugin DaemonSet ready (name varies by manifest version)
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

    # 4. ollama namespace
    ns_result = _run(["kubectl", "get", "namespace", "ollama"])
    all_ok &= _check("Namespace 'ollama' exists", ns_result.returncode == 0)

    # 5. Cerberus CA ClusterIssuer ready
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

    # 6 & 7. Ports
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
        input=_GPU_SMOKE_MANIFEST,
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
        input=_DNS_SMOKE_MANIFEST,
        text=True,
        capture_output=True,
    )
    if apply.returncode != 0:
        typer.echo(
            f"  [FAIL] Could not apply DNS smoke resources: {apply.stderr.strip()}", err=True
        )
        _cleanup_dns_smoke()
        return False

    # Wait for the nginx pod to be Running
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

    # HTTP check against test.hallm.local
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
