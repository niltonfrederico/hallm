"""k3d cluster management commands for the hallm local dev environment."""

import base64
import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import typer

from hallm.cli.base import kubectl
from hallm.cli.base.shell import check as _check
from hallm.cli.base.shell import fail as _fail
from hallm.cli.base.shell import run as _run
from hallm.cli.base.shell import run_or_fail as _run_or_fail
from hallm.core.settings import settings

app = typer.Typer(help="k3d cluster operations.")

_CLUSTER_NAME = "hallm"
_DEVICE_PLUGIN_URL = (
    "https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml"
)
_CERT_MANAGER_URL = (
    "https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml"
)
_SIGNOZ_HELM_REPO = "https://charts.signoz.io"
_SIGNOZ_NAMESPACE = "signoz"
# Manifests that are applied/managed outside the generic k8s.apply loop.
# registries.yaml is a k3s registry config file, not a Kubernetes manifest.
_SETUP_SKIP_MANIFESTS: frozenset[str] = frozenset(
    {"cerberus.yaml", "registries.yaml", "signoz-ingress.yaml"}
)

# Applied when restoring Cerberus CA from an existing cert+key in ~/.hallm/.
# Skips the self-signed bootstrap issuer and the Certificate resource — the
# secret is imported directly, so only the CA ClusterIssuer is needed.
_CERBERUS_CA_ISSUER = """\
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: cerberus-ca
  labels:
    app: cerberus
spec:
  ca:
    secretName: cerberus-ca-secret
"""


def _manifest(*parts: str) -> str:
    return (settings.K3D_PATH / "/".join(parts)).read_text()


def _mount_storage() -> None:
    """Ensure STORAGE_DEVICE is mounted at STORAGE_MOUNT_PATH.

    If the device is currently mounted elsewhere (e.g. auto-mounted by the DE),
    it is unmounted first. Requires sudo for umount/mount and mkdir under /mnt.
    """
    device = str(settings.STORAGE_DEVICE)
    mount_path = settings.STORAGE_MOUNT_PATH

    findmnt = subprocess.run(
        ["findmnt", "--source", device, "--output", "TARGET", "--noheadings"],
        text=True,
        capture_output=True,
    )
    current_mount = findmnt.stdout.strip()

    if current_mount == str(mount_path):
        typer.echo(f"  {device} already mounted at {mount_path} — skipping.")
        return

    if current_mount:
        typer.echo(f"  Unmounting {device} from {current_mount}...")
        _run_or_fail(
            ["sudo", "umount", current_mount], f"Failed to unmount {device} from {current_mount}"
        )

    typer.echo(f"  Creating mount point {mount_path}...")
    _run_or_fail(["sudo", "mkdir", "-p", str(mount_path)], f"Failed to create {mount_path}")

    typer.echo(f"  Mounting {device} at {mount_path}...")
    _run_or_fail(
        ["sudo", "mount", device, str(mount_path)], f"Failed to mount {device} at {mount_path}"
    )


def _restore_cerberus_from_files(pem_path: Path, key_path: Path) -> None:
    """Import existing cert+key as cerberus-ca-secret, then apply the CA ClusterIssuer."""
    kubectl.apply_from_cmd(
        "Secret 'cerberus-ca-secret'",
        [
            "kubectl",
            "create",
            "secret",
            "tls",
            "cerberus-ca-secret",
            "-n",
            "cert-manager",
            f"--cert={pem_path}",
            f"--key={key_path}",
            "--dry-run=client",
            "-o",
            "yaml",
        ],
    )
    kubectl.apply(_CERBERUS_CA_ISSUER, label="Cerberus CA ClusterIssuer")


def _export_cerberus_ca(pem_path: Path, key_path: Path) -> None:
    """Wait for the Cerberus CA Certificate to be issued, then save cert+key to ~/.hallm/."""
    kubectl.wait(
        "certificate/cerberus-ca",
        "Ready",
        namespace="cert-manager",
        timeout="60s",
    )
    cert_result = _run_or_fail(
        [
            "kubectl",
            "get",
            "secret",
            "cerberus-ca-secret",
            "-n",
            "cert-manager",
            "-o",
            r"jsonpath={.data.tls\.crt}",
        ],
        "Failed to retrieve cerberus-ca-secret cert",
    )
    key_result = _run_or_fail(
        [
            "kubectl",
            "get",
            "secret",
            "cerberus-ca-secret",
            "-n",
            "cert-manager",
            "-o",
            r"jsonpath={.data.tls\.key}",
        ],
        "Failed to retrieve cerberus-ca-secret key",
    )
    pem_path.write_text(base64.b64decode(cert_result.stdout.strip()).decode())
    key_path.write_text(base64.b64decode(key_result.stdout.strip()).decode())
    typer.echo(f"  Cert → {pem_path}")
    typer.echo(f"  Key  → {key_path}")


@app.command()
def setup() -> None:
    """Create the hallm k3d cluster, install the ROCm device plugin, and apply Cerberus PKI."""
    settings.SECRETS_PATH.mkdir(parents=True, exist_ok=True)
    typer.echo(f"==> Secrets directory: {settings.SECRETS_PATH}")

    typer.echo("==> Mounting SSD storage...")
    _mount_storage()

    typer.echo("\n==> Creating k3d cluster...")
    _run_or_fail(
        [
            "k3d",
            "cluster",
            "create",
            _CLUSTER_NAME,
            "--volume",
            "/dev/kfd:/dev/kfd@all",
            "--volume",
            "/dev/dri:/dev/dri@all",
            "--volume",
            f"{settings.STORAGE_MOUNT_PATH}:/var/lib/rancher/k3s/storage@all",
            "-p",
            "80:80@loadbalancer",
            "-p",
            "443:443@loadbalancer",
            "-p",
            "5432:5432@loadbalancer",
            "-p",
            "5000:5000@loadbalancer",
            "--registry-config",
            str(settings.K3D_PATH / "registries.yaml"),
        ],
        "k3d cluster create failed",
    )

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

    pem_path = settings.SECRETS_PATH / "cerberus-ca.pem"
    key_path = settings.SECRETS_PATH / "cerberus-ca.key"

    if pem_path.exists() and key_path.exists():
        typer.echo(f"\n==> Restoring Cerberus CA from {settings.SECRETS_PATH}...")
        _restore_cerberus_from_files(pem_path, key_path)
    else:
        typer.echo("\n==> Applying Cerberus PKI (self-signed CA + ClusterIssuers)...")
        kubectl.apply(_manifest("cerberus.yaml"), label="Cerberus PKI")
        typer.echo("\n==> Exporting Cerberus CA to ~/.hallm/...")
        _export_cerberus_ca(pem_path, key_path)

    typer.echo("\n==> Installing SigNoz via Helm...")
    _install_signoz()

    typer.echo("\n==> Applying service manifests from k3d/...")
    _apply_all_service_manifests()

    typer.echo("\n==> Done. Cluster is ready.")


def _install_signoz() -> None:
    """Install / upgrade the SigNoz Helm release in the signoz namespace."""
    add_repo = _run(["helm", "repo", "add", "signoz", _SIGNOZ_HELM_REPO])
    if add_repo.returncode != 0 and "already exists" not in add_repo.stderr:
        _fail(f"helm repo add signoz failed:\n{add_repo.stderr}")

    _run_or_fail(["helm", "repo", "update"], "helm repo update failed")

    _run(
        ["kubectl", "create", "namespace", _SIGNOZ_NAMESPACE]
    )  # idempotent: ignore "already exists"

    values_file = settings.K3D_PATH / "helm" / "signoz-values.yaml"
    _run_or_fail(
        [
            "helm",
            "upgrade",
            "--install",
            "signoz",
            "signoz/signoz",
            "-n",
            _SIGNOZ_NAMESPACE,
            "-f",
            str(values_file),
        ],
        "helm install signoz failed",
    )

    kubectl.apply(_manifest("signoz-ingress.yaml"), label="SigNoz Ingress")


def _apply_all_service_manifests() -> None:
    """Apply every top-level k3d/*.yaml manifest except the ones managed elsewhere."""
    for manifest in sorted(settings.K3D_PATH.glob("*.yaml")):
        if manifest.name in _SETUP_SKIP_MANIFESTS:
            continue
        kubectl.apply(manifest.read_text(), label=manifest.stem)


@app.command()
def nuke(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    volumes: bool = typer.Option(
        False,
        "--volumes",
        help="Also wipe persistent volume data from the host storage mount.",
    ),
) -> None:
    """Delete the hallm k3d cluster and all its resources.

    By default the host storage mount (PVC data) is preserved.
    Pass --volumes to also delete it.
    """
    mount_path = settings.STORAGE_MOUNT_PATH
    msg = f"This will permanently delete the '{_CLUSTER_NAME}' cluster"
    if volumes:
        msg += f" AND all data in {mount_path}"
    msg += ". Continue?"
    if not yes:
        typer.confirm(msg, abort=True)

    _run_or_fail(["k3d", "cluster", "delete", _CLUSTER_NAME], "k3d cluster delete failed")
    typer.echo(f"\nCluster '{_CLUSTER_NAME}' deleted.")

    if volumes:
        typer.echo(f"\n==> Wiping persistent volume data at {mount_path}...")
        _run_or_fail(["sudo", "rm", "-rf", str(mount_path)], f"Failed to wipe {mount_path}")
        typer.echo("  Done.")


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


@app.command("get-cert")
def get_cert() -> None:
    """Fetch the Cerberus CA cert and key from the cluster and save them to ~/.hallm/.

    Writes cerberus-ca.pem and cerberus-ca.key so that subsequent cluster setups
    can reuse the same CA instead of generating a new self-signed one.
    """
    pem_path = settings.SECRETS_PATH / "cerberus-ca.pem"
    key_path = settings.SECRETS_PATH / "cerberus-ca.key"
    settings.SECRETS_PATH.mkdir(parents=True, exist_ok=True)

    cert_result = _run_or_fail(
        [
            "kubectl",
            "get",
            "secret",
            "cerberus-ca-secret",
            "-n",
            "cert-manager",
            "-o",
            r"jsonpath={.data.tls\.crt}",
        ],
        "Failed to retrieve cerberus-ca-secret",
    )
    encoded_cert = cert_result.stdout.strip()
    if not encoded_cert:
        _fail("cerberus-ca-secret/tls.crt is empty — has the Cerberus PKI been applied?")

    key_result = _run_or_fail(
        [
            "kubectl",
            "get",
            "secret",
            "cerberus-ca-secret",
            "-n",
            "cert-manager",
            "-o",
            r"jsonpath={.data.tls\.key}",
        ],
        "Failed to retrieve cerberus-ca-secret",
    )
    encoded_key = key_result.stdout.strip()
    if not encoded_key:
        _fail("cerberus-ca-secret/tls.key is empty — has the Cerberus PKI been applied?")

    pem_path.write_text(base64.b64decode(encoded_cert).decode())
    key_path.write_text(base64.b64decode(encoded_key).decode())
    typer.echo(f"Cert → {pem_path}")
    typer.echo(f"Key  → {key_path}")
