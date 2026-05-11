"""Preflight checks for the local rootless Docker / k3d environment."""

import os
from collections.abc import Callable
from pathlib import Path

import typer

from hallm.cli.base import docker as _docker
from hallm.cli.base.shell import check as _check
from hallm.cli.base.shell import fail as _fail
from hallm.cli.base.shell import run as _run
from hallm.core.settings import ClusterSettings
from hallm.core.settings import settings


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
    if not ClusterSettings.CGROUP_DELEGATE_FILE.exists():
        return False, f"Write {ClusterSettings.CGROUP_DELEGATE_FILE} and re-login."
    controllers_file = Path(
        f"/sys/fs/cgroup/user.slice/user-{os.getuid()}.slice/cgroup.controllers"
    )
    try:
        controllers = set(controllers_file.read_text().split())
    except OSError:
        return False, f"Could not read {controllers_file}."
    missing = ClusterSettings.REQUIRED_CGROUP_CONTROLLERS - controllers
    if missing:
        return False, (
            f"Missing delegated cgroup controllers: {sorted(missing)}. "
            "Re-login (or reboot) after writing the systemd drop-in."
        )
    return True, None


def _check_gpu_devices() -> tuple[bool, str | None]:
    missing = [str(d) for d in ClusterSettings.GPU_DEVICES if not os.access(d, os.R_OK | os.W_OK)]
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


def preflight() -> None:
    """Verify rootless Docker, cgroups, GPU access, and storage before cluster setup."""
    _run_preflight()
    typer.echo("\nAll preflight checks passed.")
