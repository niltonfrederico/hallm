"""Targeted diagnostics for rootless Docker / k3d issues."""

import os
from pathlib import Path

import typer

from hallm.cli.base import docker as _docker
from hallm.cli.base.shell import check as _check
from hallm.core.settings import ClusterSettings
from hallm.core.settings import settings


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
    for dev in ClusterSettings.GPU_DEVICES:
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
