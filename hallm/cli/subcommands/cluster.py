"""Cluster lifecycle commands for the hallm local dev environment.

Covers the full lifecycle of the k3d cluster:
``preflight``, ``diagnose``, ``mount``, ``setup``, ``nuke``, ``healthcheck``.
"""

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
from hallm.cli.subcommands import db as _db
from hallm.cli.subcommands import secrets as _secrets
from hallm.cli.subcommands import signoz as _signoz
from hallm.core.settings import settings

app = typer.Typer(help="Cluster lifecycle operations.", no_args_is_help=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CLUSTER_NAME = "hallm"
_DEFAULT_NAMESPACE = "default"
_UNREGISTRY_HOST = "unregistry.hallm.local"
_DEVICE_PLUGIN_URL = (
    "https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml"
)
_CERT_MANAGER_URL = (
    "https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml"
)
# Manifests applied/managed outside the generic apply loop.
# registries.yaml is a k3s registry config file, not a Kubernetes manifest.
# traefik-config.yaml must be applied before postgres so the bootstrap can
# reach postgres through the Traefik TCP entrypoint.
# signoz-{ingress,extras}.yaml are owned by `hallm signoz bootstrap`.
_SETUP_SKIP_MANIFESTS: frozenset[str] = frozenset(
    {
        "cerberus.yaml",
        "postgres.yaml",
        "registries.yaml",
        "signoz-ingress.yaml",
        "signoz-extras.yaml",
        "traefik-config.yaml",
    }
)

_REQUIRED_NAMESPACES: tuple[str, ...] = ("signoz", "docs")

_GPU_DEVICES: tuple[Path, ...] = (Path("/dev/kfd"), Path("/dev/dri/renderD128"))
_CGROUP_DELEGATE_FILE = Path("/etc/systemd/system/user@.service.d/delegate.conf")
_REQUIRED_CGROUP_CONTROLLERS: frozenset[str] = frozenset({"cpu", "cpuset", "io"})


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


def _preflight_checks() -> tuple[tuple[str, Callable[[], tuple[bool, str | None]]], ...]:
    return (
        (f"Docker context '{settings.DOCKER_CONTEXT}' exists", _check_docker_context_exists),
        ("Rootless Docker daemon reachable", _check_docker_daemon_reachable),
        ("Privileged ports (<=80) allowed for rootless", _check_unprivileged_ports),
        ("cgroup v2 delegation configured for user slice", _check_cgroup_delegation),
        ("GPU devices accessible (/dev/kfd, /dev/dri/renderD128)", _check_gpu_devices),
        (
            f"Storage mount {settings.STORAGE_MOUNT_PATH} owned by current user",
            _check_storage_owner,
        ),
    )


def _run_preflight() -> None:
    """Run all preflight checks; exit 1 with hints if any fail."""
    all_ok = True
    for label, check_fn in _preflight_checks():
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
# Diagnose
# ---------------------------------------------------------------------------


def _cgroup_memory_ok(uid: int) -> tuple[str, bool]:
    """Read memory.max from the user cgroup slice; return (display, ok)."""
    mem_path = Path(f"/sys/fs/cgroup/user.slice/user-{uid}.slice/memory.max")
    try:
        raw = mem_path.read_text().strip()
    except OSError:
        return f"cannot read {mem_path}", False
    if raw == "max":
        return "unlimited", True
    try:
        limit_mb = int(raw) // (1024 * 1024)
    except ValueError:
        return f"unreadable ({raw!r})", False
    return f"{limit_mb} MB", limit_mb >= 2048


@app.command()
def diagnose(
    context: str = typer.Option(
        settings.DOCKER_CONTEXT,
        "--context",
        help="Docker context to target. Defaults to the rootless hallm context.",
    ),
) -> None:
    """Run targeted diagnostics to isolate rootless Docker / k3d issues.

    Tests the Docker context step-by-step: daemon reachability, basic container
    execution, low-port binding, GPU device mounts, storage volume access, and
    user cgroup memory — the most common failure points when k3d hangs in
    rootless mode.
    """
    if context != settings.DOCKER_CONTEXT:
        settings.DOCKER_CONTEXT = context

    ctx = settings.DOCKER_CONTEXT
    all_ok = True

    typer.echo(f"==> Diagnostics for Docker context '{ctx}'\n")

    typer.echo("--- Daemon info ---")
    _docker.run(
        [
            "docker",
            "info",
            "--format",
            "Server Version: {{.ServerVersion}}\n"
            "Security Options: {{.SecurityOptions}}\n"
            "Cgroup Driver: {{.CgroupDriver}} (v{{.CgroupVersion}})\n"
            "Logging Driver: {{.LoggingDriver}}",
        ],
        stream=True,
    )

    typer.echo("\n--- Container tests ---")
    r = _docker.run(["docker", "run", "--rm", "alpine", "echo", "ok"])
    all_ok &= _check("Basic container execution", r.returncode == 0)
    if r.returncode != 0:
        typer.echo(f"         stderr: {r.stderr.strip()}")

    r = _docker.run(["docker", "run", "--rm", "-p", "80:80", "alpine", "echo", "ok"])
    all_ok &= _check("Bind port 80 (required for Traefik ingress)", r.returncode == 0)
    if r.returncode != 0:
        typer.echo(f"         stderr: {r.stderr.strip()}")

    typer.echo("\n--- GPU device mounts ---")
    for dev in _GPU_DEVICES:
        r = _docker.run(["docker", "run", "--rm", "--device", str(dev), "alpine", "ls", str(dev)])
        all_ok &= _check(f"Mount {dev}", r.returncode == 0)
        if r.returncode != 0:
            typer.echo(f"         stderr: {r.stderr.strip()}")

    typer.echo("\n--- Storage volume ---")
    mount = settings.STORAGE_MOUNT_PATH
    r = _docker.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{mount}:/mnt/hallm-test:ro",
            "alpine",
            "ls",
            "/mnt/hallm-test",
        ]
    )
    all_ok &= _check(f"Mount {mount} into container", r.returncode == 0)
    if r.returncode != 0:
        typer.echo(f"         stderr: {r.stderr.strip()}")

    typer.echo("\n--- User cgroup memory ---")
    display, mem_ok = _cgroup_memory_ok(os.getuid())
    all_ok &= _check(f"Memory limit ≥ 2 GB (actual: {display})", mem_ok)
    if not mem_ok:
        typer.echo(
            "         hint: k3s needs ~2 GB. Check cgroup delegation or "
            "raise the user slice memory limit."
        )

    typer.echo("\n--- k3d version ---")
    _docker.run(["k3d", "version"], stream=True)

    typer.echo("\n--- Existing cluster state ---")
    _docker.run(["k3d", "cluster", "list"], stream=True)

    typer.echo()
    if all_ok:
        typer.echo("All diagnostic checks passed.")
    else:
        typer.echo("One or more checks failed — see hints above.")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Mount
# ---------------------------------------------------------------------------


@app.command()
def mount() -> None:
    """Mount the SSD storage device at the configured mount path."""
    typer.echo("==> Mounting SSD storage...")
    _mount_storage()
    typer.echo("Done.")


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def _ensure_namespaces() -> None:
    """Create any required namespace that doesn't already exist (idempotent)."""
    for ns in _REQUIRED_NAMESPACES:
        manifest = f"apiVersion: v1\nkind: Namespace\nmetadata:\n  name: {ns}\n"
        kubectl.apply(manifest, label=f"namespace/{ns}")


def _setup_postgres() -> None:
    """Apply the postgres manifest, wait for the deployment to be ready, then bootstrap the DB."""
    kubectl.apply(_manifest("postgres.yaml"), label="postgres")
    kubectl.wait("deploy/postgres", "Available", namespace=_DEFAULT_NAMESPACE, timeout="180s")
    typer.echo("\n==> Running database bootstrap...")
    _db._run_bootstrap()


def _apply_all_service_manifests() -> None:
    """Apply every top-level k8s/*.yaml manifest except the ones managed elsewhere."""
    for manifest in sorted(settings.K8S_PATH.glob("*.yaml")):
        if manifest.name in _SETUP_SKIP_MANIFESTS:
            continue
        kubectl.apply(manifest.read_text(), label=manifest.stem)


@app.command()
def setup(
    context: str = typer.Option(
        settings.DOCKER_CONTEXT,
        "--context",
        help=(
            "Docker context for k3d/docker calls. "
            "Defaults to the rootless hallm context; pass 'default' to use the "
            "standard Docker daemon for debugging."
        ),
    ),
) -> None:
    """Create the hallm k3d cluster, install the ROCm device plugin, and apply Cerberus PKI."""
    if context != settings.DOCKER_CONTEXT:
        typer.echo(f"==> Docker context: {context}")
        settings.DOCKER_CONTEXT = context

    typer.echo("==> Running preflight checks...")
    _run_preflight()

    settings.SECRETS_PATH.mkdir(parents=True, exist_ok=True)
    typer.echo(f"==> Secrets directory: {settings.SECRETS_PATH}")

    typer.echo("==> Mounting SSD storage...")
    _mount_storage()

    typer.echo("\n==> Creating k3d cluster (first run may take ~10 min while k3s pulls images)...")
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
            "10432:5432@loadbalancer",
            "-p",
            "10300:5000@loadbalancer",
            "-p",
            "10379:6379@loadbalancer",
            "--registry-config",
            str(settings.K8S_PATH / "registries.yaml"),
            "--k3s-arg",
            "--kubelet-arg=feature-gates=KubeletInUserNamespace=true@server:*",
            "--timeout",
            "15m0s",
        ],
        "k3d cluster create failed",
        stream=True,
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

        typer.echo("\n==> Ensuring required namespaces exist...")
        _ensure_namespaces()

        typer.echo("\n==> Configuring Traefik TCP entrypoints (postgres, valkey)...")
        kubectl.apply(_manifest("traefik-config.yaml"), label="Traefik entrypoints")

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
            _secrets._restore_cerberus_from_files(pem_path, key_path)
        else:
            typer.echo("\n==> Applying Cerberus PKI (self-signed CA + ClusterIssuers)...")
            kubectl.apply(_manifest("cerberus.yaml"), label="Cerberus PKI")
            typer.echo("\n==> Exporting Cerberus CA to ~/.hallm/...")
            _secrets._export_cerberus_ca(pem_path, key_path)

        typer.echo("\n==> Trusting Cerberus CA for Docker registry...")
        _secrets._configure_docker_registry_cert(pem_path)

        typer.echo("\n==> Syncing secrets to cluster...")
        _secrets._sync_secrets()

        typer.echo("\n==> Setting up postgres...")
        _setup_postgres()

        typer.echo("\n==> Applying service manifests from k8s/...")
        _apply_all_service_manifests()

        typer.echo("\n==> Bootstrapping SigNoz...")
        _signoz._run_bootstrap()

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


class _SmokeAborted(Exception):
    """Internal sentinel: the smoke pod entered a terminal failure state."""


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
