"""Kubernetes operations for the hallm local dev environment.

The commands fall into two groups:

* **Cluster lifecycle** — ``preflight``, ``setup``, ``healthcheck``, ``nuke``,
  ``get-cert``: provision, verify, and tear down the local k3d cluster, and
  manage the Cerberus PKI cert/key on the host.
* **Cluster operations** — ``sync-secrets``, ``remove``, ``seed-heimdall``:
  routine ops against an already-running cluster.
"""

import base64
import json
import os
import socket
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

import typer

from hallm.cli.base import docker as _docker
from hallm.cli.base import kubectl
from hallm.cli.base.poll import poll_until
from hallm.cli.base.shell import check as _check
from hallm.cli.base.shell import fail as _fail
from hallm.cli.base.shell import run as _run
from hallm.cli.base.shell import run_or_fail as _run_or_fail
from hallm.core.settings import settings

app = typer.Typer(help="Kubernetes operations.", no_args_is_help=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CLUSTER_NAME = "hallm"
_DEFAULT_NAMESPACE = "default"
_DEVICE_PLUGIN_URL = (
    "https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml"
)
_CERT_MANAGER_URL = (
    "https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml"
)
_SIGNOZ_HELM_REPO = "https://charts.signoz.io"
_SIGNOZ_NAMESPACE = "signoz"
# Manifests applied/managed outside the generic apply loop.
# registries.yaml is a k3s registry config file, not a Kubernetes manifest.
_SETUP_SKIP_MANIFESTS: frozenset[str] = frozenset(
    {"cerberus.yaml", "registries.yaml", "signoz-ingress.yaml"}
)

# Applied when restoring Cerberus CA from an existing cert+key in ~/.hallm/.
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

_GPU_DEVICES: tuple[Path, ...] = (Path("/dev/kfd"), Path("/dev/dri/renderD128"))
_CGROUP_DELEGATE_FILE = Path("/etc/systemd/system/user@.service.d/delegate.conf")
_REQUIRED_CGROUP_CONTROLLERS: frozenset[str] = frozenset({"cpu", "cpuset", "io"})

# Apps registered in Heimdall after the cluster is up.
# Each tuple is (title, url, colour). Heimdall fills in default icons.
_HEIMDALL_APPS: tuple[tuple[str, str, str], ...] = (
    ("Glitchtip", "https://glitchtip.hallm.local", "#ff5722"),
    ("SigNoz", "https://signoz.hallm.local", "#e75480"),
    ("Habitica", "https://habitica.hallm.local", "#6f4cba"),
    ("OpenClaw", "https://openclaw.hallm.local", "#0d6efd"),
    ("Gotify", "https://gotify.hallm.local", "#34a853"),
    ("Paperless", "https://paperless.hallm.local", "#1f9d55"),
    ("OTS", "https://ots.hallm.local", "#dc3545"),
    ("ActivityWatch", "https://aw.hallm.local", "#fd7e14"),
    ("Spotify", "https://spotify.hallm.local", "#1db954"),
    ("RustFS", "https://rustfs.hallm.local", "#b7410e"),
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _manifest(*parts: str) -> str:
    return (settings.K8S_PATH / "/".join(parts)).read_text()


def _mount_storage() -> None:
    """Ensure STORAGE_DEVICE is mounted at STORAGE_MOUNT_PATH."""
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


def _read_cerberus_secret_data(field: str) -> str:
    """Return the raw base64 value of cerberus-ca-secret/<field>."""
    result = _run_or_fail(
        [
            "kubectl",
            "get",
            "secret",
            "cerberus-ca-secret",
            "-n",
            "cert-manager",
            "-o",
            rf"jsonpath={{.data.{field.replace('.', r'\.')}}}",
        ],
        f"Failed to retrieve cerberus-ca-secret/{field}",
    )
    return result.stdout.strip()


def _export_cerberus_ca(pem_path: Path, key_path: Path) -> None:
    """Wait for the Cerberus CA Certificate to be issued, then save cert+key to ~/.hallm/."""
    kubectl.wait(
        "certificate/cerberus-ca",
        "Ready",
        namespace="cert-manager",
        timeout="60s",
    )
    pem_path.write_text(base64.b64decode(_read_cerberus_secret_data("tls.crt")).decode())
    key_path.write_text(base64.b64decode(_read_cerberus_secret_data("tls.key")).decode())
    typer.echo(f"  Cert → {pem_path}")
    typer.echo(f"  Key  → {key_path}")


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def _check_docker_context_exists() -> tuple[bool, str | None]:
    result = _run(["docker", "context", "inspect", settings.DOCKER_CONTEXT])
    if result.returncode == 0:
        return True, None
    return False, "Run scripts/install-rootless-docker.sh."


def _check_docker_daemon_reachable() -> tuple[bool, str | None]:
    result = _docker.run(["docker", "info"])
    if result.returncode == 0:
        return True, None
    return False, "Check 'systemctl --user status docker'."


def _check_unprivileged_ports() -> tuple[bool, str | None]:
    try:
        start = int(Path("/proc/sys/net/ipv4/ip_unprivileged_port_start").read_text().strip())
    except OSError, ValueError:
        return False, "Could not read /proc/sys/net/ipv4/ip_unprivileged_port_start."
    if start <= 80:
        return True, None
    return False, (
        "Drop /etc/sysctl.d/90-hallm-rootless.conf with "
        "'net.ipv4.ip_unprivileged_port_start=80' and run 'sudo sysctl --system'."
    )


def _check_cgroup_delegation() -> tuple[bool, str | None]:
    if not _CGROUP_DELEGATE_FILE.exists():
        return False, f"Write {_CGROUP_DELEGATE_FILE} and re-login."
    controllers_file = Path(
        f"/sys/fs/cgroup/user.slice/user-{os.getuid()}.slice/cgroup.controllers"
    )
    try:
        controllers = set(controllers_file.read_text().split())
    except OSError:
        return False, f"Could not read {controllers_file}."
    missing = _REQUIRED_CGROUP_CONTROLLERS - controllers
    if missing:
        return False, (
            f"Missing delegated cgroup controllers: {sorted(missing)}. "
            "Re-login (or reboot) after writing the systemd drop-in."
        )
    return True, None


def _check_gpu_devices() -> tuple[bool, str | None]:
    missing = [str(d) for d in _GPU_DEVICES if not os.access(d, os.R_OK | os.W_OK)]
    if missing:
        return False, (
            f"No R/W access to {missing}. Run 'sudo usermod -aG render,video $USER' and re-login."
        )
    return True, None


def _check_storage_owner() -> tuple[bool, str | None]:
    mount_path = settings.STORAGE_MOUNT_PATH
    if not mount_path.exists():
        return False, f"{mount_path} does not exist yet — setup will mount it."
    if mount_path.stat().st_uid != os.getuid():
        return False, f"Run 'sudo chown -R $USER:$USER {mount_path}'."
    return True, None


_PREFLIGHT_CHECKS: tuple[tuple[str, Callable[[], tuple[bool, str | None]]], ...] = (
    (f"Docker context '{settings.DOCKER_CONTEXT}' exists", _check_docker_context_exists),
    ("Rootless Docker daemon reachable", _check_docker_daemon_reachable),
    ("Privileged ports (<=80) allowed for rootless", _check_unprivileged_ports),
    ("cgroup v2 delegation configured for user slice", _check_cgroup_delegation),
    ("GPU devices accessible (/dev/kfd, /dev/dri/renderD128)", _check_gpu_devices),
    (f"Storage mount {settings.STORAGE_MOUNT_PATH} owned by current user", _check_storage_owner),
)


def _run_preflight() -> None:
    """Run all preflight checks; exit 1 with hints if any fail."""
    all_ok = True
    for label, check_fn in _PREFLIGHT_CHECKS:
        ok, hint = check_fn()
        all_ok &= _check(label, ok)
        if not ok and hint:
            typer.echo(f"         hint: {hint}")
    if not all_ok:
        _fail("Preflight checks failed — fix the items above and retry.")


@app.command()
def preflight() -> None:
    """Verify rootless Docker, cgroups, GPU access, and storage before cluster setup."""
    _run_preflight()
    typer.echo("\nAll preflight checks passed.")


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def _install_signoz() -> None:
    """Install / upgrade the SigNoz Helm release in the signoz namespace."""
    add_repo = _run(["helm", "repo", "add", "signoz", _SIGNOZ_HELM_REPO])
    if add_repo.returncode != 0 and "already exists" not in add_repo.stderr:
        _fail(f"helm repo add signoz failed:\n{add_repo.stderr}")

    _run_or_fail(["helm", "repo", "update"], "helm repo update failed")

    _run(
        ["kubectl", "create", "namespace", _SIGNOZ_NAMESPACE]
    )  # idempotent: ignore "already exists"

    values_file = settings.K8S_PATH / "helm" / "signoz-values.yaml"
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
    """Apply every top-level k8s/*.yaml manifest except the ones managed elsewhere."""
    for manifest in sorted(settings.K8S_PATH.glob("*.yaml")):
        if manifest.name in _SETUP_SKIP_MANIFESTS:
            continue
        kubectl.apply(manifest.read_text(), label=manifest.stem)


@app.command()
def setup() -> None:
    """Create the hallm k3d cluster, install the ROCm device plugin, and apply Cerberus PKI."""
    typer.echo("==> Running preflight checks...")
    _run_preflight()

    settings.SECRETS_PATH.mkdir(parents=True, exist_ok=True)
    typer.echo(f"==> Secrets directory: {settings.SECRETS_PATH}")

    typer.echo("==> Mounting SSD storage...")
    _mount_storage()

    typer.echo("\n==> Creating k3d cluster...")
    _docker.run_or_fail(
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
            str(settings.K8S_PATH / "registries.yaml"),
        ],
        "k3d cluster create failed",
    )

    try:
        typer.echo("\n==> Waiting for Kubernetes API server to be ready...")
        api_ready = poll_until(
            lambda: _run(["kubectl", "get", "nodes"]).returncode == 0,
            timeout=120,
            interval=3.0,
        )
        if not api_ready:
            _fail("Kubernetes API server did not become ready in time")

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

        typer.echo("\n==> Applying service manifests from k8s/...")
        _apply_all_service_manifests()

        typer.echo("\n==> Done. Cluster is ready.")
    except Exception:
        typer.echo("\n==> Setup failed — nuking cluster to clean up...")
        _docker.run(["k3d", "cluster", "delete", _CLUSTER_NAME])
        raise


# ---------------------------------------------------------------------------
# Nuke
# ---------------------------------------------------------------------------


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

    _docker.run_or_fail(["k3d", "cluster", "delete", _CLUSTER_NAME], "k3d cluster delete failed")
    typer.echo(f"\nCluster '{_CLUSTER_NAME}' deleted.")

    if volumes:
        typer.echo(f"\n==> Wiping persistent volume data at {mount_path}...")
        _run_or_fail(["sudo", "rm", "-rf", str(mount_path)], f"Failed to wipe {mount_path}")
        typer.echo("  Done.")


# ---------------------------------------------------------------------------
# Healthcheck
# ---------------------------------------------------------------------------


def _cluster_running_via_k3d() -> bool:
    """Check that the named k3d cluster has at least one server running."""
    result = _docker.run(["k3d", "cluster", "list", "-o", "json"])
    if result.returncode != 0:
        return False
    try:
        clusters: list[dict[str, object]] = json.loads(result.stdout)
    except json.JSONDecodeError, ValueError, TypeError:
        return False
    return any(
        c.get("name") == _CLUSTER_NAME and int(c.get("serversRunning", 0) or 0) >= 1
        for c in clusters
    )


def _gpu_visible_to_kubernetes() -> bool:
    nodes = kubectl.get_json(["node"])
    if not isinstance(nodes, dict):
        return False
    items = nodes.get("items", []) or []
    for item in items:
        try:
            allocatable = int(item.get("status", {}).get("allocatable", {}).get("amd.com/gpu", "0"))
        except TypeError, ValueError:
            continue
        if allocatable >= 1:
            return True
    return False


def _amdgpu_daemonset_ready() -> bool:
    all_ds = kubectl.get_json(["ds", "-n", "kube-system"])
    if not isinstance(all_ds, dict):
        return False
    amdgpu_ds = next(
        (
            item
            for item in all_ds.get("items", []) or []
            if "amdgpu" in item.get("metadata", {}).get("name", "")
        ),
        None,
    )
    if not amdgpu_ds:
        return False
    status = amdgpu_ds.get("status", {})
    desired = status.get("desiredNumberScheduled", -1)
    ready = status.get("numberReady", 0)
    return desired >= 1 and desired == ready


def _cerberus_issuer_ready() -> bool:
    issuer = kubectl.get_json(["clusterissuer", "cerberus-ca"])
    if not isinstance(issuer, dict):
        return False
    conditions = issuer.get("status", {}).get("conditions", []) or []
    return any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions)


def _port_reachable(port: int) -> bool:
    try:
        with socket.create_connection(("localhost", port), timeout=3):
            return True
    except OSError:
        return False


@app.command()
def healthcheck() -> None:
    """Verify the hallm cluster, GPU, Cerberus issuer, ports, and run smoke tests."""
    all_ok = True

    typer.echo("==> Static checks")
    all_ok &= _check(f"Cluster '{_CLUSTER_NAME}' is running", _cluster_running_via_k3d())
    all_ok &= _check("GPU (amd.com/gpu) visible to Kubernetes", _gpu_visible_to_kubernetes())
    all_ok &= _check("ROCm device plugin DaemonSet ready", _amdgpu_daemonset_ready())
    all_ok &= _check("Cerberus CA ClusterIssuer ready", _cerberus_issuer_ready())
    for port in (80, 443):
        all_ok &= _check(f"Port {port} reachable on localhost", _port_reachable(port))

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


def _pod_phase(pod: str) -> str:
    return subprocess.run(
        ["kubectl", "get", "pod", pod, "-o", "jsonpath={.status.phase}"],
        text=True,
        capture_output=True,
    ).stdout.strip()


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

    failed_phases = {"Failed", "Unknown"}

    def _ready() -> bool:
        phase = _pod_phase("hallm-gpu-smoke")
        if phase == "Succeeded":
            return True
        if phase in failed_phases:
            raise _SmokeAborted()
        return False

    try:
        ok = poll_until(_ready, timeout=30)
    except _SmokeAborted:
        ok = False

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

    def _pod_running() -> bool:
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
        return result.stdout.strip() == "Running"

    pod_ok = poll_until(_pod_running, timeout=30)
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


class _SmokeAborted(Exception):
    """Internal sentinel: the smoke pod entered a terminal failure state."""


# ---------------------------------------------------------------------------
# get-cert
# ---------------------------------------------------------------------------


@app.command("get-cert")
def get_cert() -> None:
    """Fetch the Cerberus CA cert and key from the cluster and save them to ~/.hallm/.

    Writes cerberus-ca.pem and cerberus-ca.key so that subsequent cluster setups
    can reuse the same CA instead of generating a new self-signed one.
    """
    pem_path = settings.SECRETS_PATH / "cerberus-ca.pem"
    key_path = settings.SECRETS_PATH / "cerberus-ca.key"
    settings.SECRETS_PATH.mkdir(parents=True, exist_ok=True)

    encoded_cert = _read_cerberus_secret_data("tls.crt")
    if not encoded_cert:
        _fail("cerberus-ca-secret/tls.crt is empty — has the Cerberus PKI been applied?")

    encoded_key = _read_cerberus_secret_data("tls.key")
    if not encoded_key:
        _fail("cerberus-ca-secret/tls.key is empty — has the Cerberus PKI been applied?")

    pem_path.write_text(base64.b64decode(encoded_cert).decode())
    key_path.write_text(base64.b64decode(encoded_key).decode())
    typer.echo(f"Cert → {pem_path}")
    typer.echo(f"Key  → {key_path}")


# ---------------------------------------------------------------------------
# Cluster operations
# ---------------------------------------------------------------------------


@app.command("sync-secrets")
def sync_secrets() -> None:
    """Sync ~/.hallm/*.env files → Kubernetes Secrets.

    Each <secret-name>.env file in ~/.hallm/ is applied as a Secret named
    <secret-name>.  A file named exactly .env is applied as 'hallm-env'.
    """
    secrets_dir = settings.SECRETS_PATH
    secrets_dir.mkdir(parents=True, exist_ok=True)

    sources: list[tuple[str, Path]] = [
        (env_file.stem, env_file)
        for env_file in sorted(secrets_dir.glob("*.env"))
        if env_file.name != ".env"
    ]
    hallm_env = secrets_dir / ".env"
    if hallm_env.exists():
        sources.append(("hallm-env", hallm_env))

    if not sources:
        typer.echo(f"No .env files found in {secrets_dir}. Add <secret-name>.env files to sync.")
        return

    for secret_name, env_file in sources:
        typer.echo(f"==> Syncing {env_file.name} → Secret '{secret_name}'...")
        kubectl.apply_from_cmd(
            f"Secret '{secret_name}'",
            [
                "kubectl",
                "create",
                "secret",
                "generic",
                secret_name,
                f"--from-env-file={env_file}",
                "--dry-run=client",
                "-o",
                "yaml",
            ],
        )

    typer.echo("\nDone.")


@app.command()
def remove(
    name: str = typer.Argument(
        ..., help="Manifest name in k8s/ (without .yaml), e.g. 'ollama', 'postgres'"
    ),
    namespace: str = typer.Option(
        _DEFAULT_NAMESPACE, "--namespace", "-n", help="Kubernetes namespace"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
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


@app.command("seed-heimdall")
def seed_heimdall(
    namespace: str = typer.Option(_DEFAULT_NAMESPACE, "--namespace", "-n"),
    timeout: int = typer.Option(120, "--timeout", help="Seconds to wait for Heimdall DB"),
) -> None:
    """Populate Heimdall with hallm-managed apps via sqlite3 INSERT OR IGNORE."""
    typer.echo("==> Locating Heimdall pod...")
    pod_name = _heimdall_pod(namespace)
    if not pod_name:
        _fail("No Heimdall pod found. Apply k8s/heimdall.yaml first.")

    typer.echo(f"==> Waiting up to {timeout}s for Heimdall items table...")
    if not _wait_for_heimdall_db(pod_name, namespace, timeout):
        _fail("Heimdall items table did not appear within timeout.")

    typer.echo("==> Seeding apps...")
    sql_lines = [
        f"INSERT OR IGNORE INTO items (title, url, colour, type, pinned, "
        f'"order", created_at, updated_at) VALUES '
        f"('{title}', '{url}', '{colour}', 0, 1, {idx}, datetime('now'), datetime('now'));"
        for idx, (title, url, colour) in enumerate(_HEIMDALL_APPS)
    ]
    script = (
        "sqlite3 /config/www/SimpleSettings/database.sqlite <<'SQL'\n"
        + "\n".join(sql_lines)
        + "\nSQL\n"
    )

    result = subprocess.run(
        ["kubectl", "exec", "-n", namespace, "-i", pod_name, "--", "sh", "-c", script],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        _fail(f"sqlite3 seed failed:\n{result.stderr}")

    typer.echo(f"\nSeeded {len(_HEIMDALL_APPS)} apps. Visit https://heimdall.hallm.local")


def _heimdall_pod(namespace: str) -> str | None:
    result = subprocess.run(
        [
            "kubectl",
            "get",
            "pod",
            "-n",
            namespace,
            "-l",
            "app=heimdall",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ],
        text=True,
        capture_output=True,
    )
    return result.stdout.strip() or None


def _wait_for_heimdall_db(pod_name: str, namespace: str, timeout: int) -> bool:
    probe = (
        "sqlite3 /config/www/SimpleSettings/database.sqlite "
        '\'SELECT name FROM sqlite_master WHERE type="table" AND name="items";\''
    )

    def _has_items_table() -> bool:
        result = subprocess.run(
            ["kubectl", "exec", "-n", namespace, pod_name, "--", "sh", "-c", probe],
            text=True,
            capture_output=True,
        )
        return result.returncode == 0 and "items" in result.stdout

    return poll_until(_has_items_table, timeout=timeout, interval=3.0)
