"""End-to-end cluster healthcheck: static checks + smoke tests."""

import json
import socket
import subprocess
import urllib.error
import urllib.request

import typer

from hallm.cli.base import docker as _docker
from hallm.cli.base import kubectl
from hallm.cli.base.poll import poll_until
from hallm.cli.base.shell import check as _check
from hallm.core import workspace
from hallm.core.settings import ClusterSettings


def _manifest(*parts: str) -> str | None:
    """Read a smoke-test manifest from the repo, or None if no checkout is discoverable."""
    repo = workspace.find_repo()
    if repo is None:
        return None
    return (repo / "k8s" / "/".join(parts)).read_text()


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
        c.get("name") == ClusterSettings.NAME and int(c.get("serversRunning", 0) or 0) >= 1
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
    manifest = _manifest("test", "gpu-smoke.yaml")
    if manifest is None:
        typer.echo("  [SKIP] No hallm checkout discoverable — GPU smoke test skipped.")
        return True
    apply = subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=manifest,
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


def _dns_smoke_test() -> bool:
    """Deploy nginx + Ingress for test.hallm.local, verify HTTP, clean up. Return True on pass."""
    manifest = _manifest("test", "dns-smoke.yaml")
    if manifest is None:
        typer.echo("  [SKIP] No hallm checkout discoverable — DNS smoke test skipped.")
        return True
    apply = subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=manifest,
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


def healthcheck() -> None:
    """Verify the hallm cluster, GPU, Cerberus issuer, ports, and run smoke tests."""
    all_ok = True

    typer.echo("==> Static checks")
    all_ok &= _check(f"Cluster '{ClusterSettings.NAME}' is running", _cluster_running_via_k3d())
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
