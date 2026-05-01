"""Low-level shell helpers for CLI subcommands."""

import os
import subprocess
from typing import NoReturn

import typer


def run(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run a shell command, echoing it first, and return the completed process.

    If ``env`` is provided, its entries are merged on top of ``os.environ``
    before being passed to the subprocess. When ``DOCKER_CONTEXT`` is set in
    the override, it is appended to the echoed command line so the routing is
    visible in failure logs.
    """
    suffix = ""
    if env and "DOCKER_CONTEXT" in env:
        suffix = f"  [ctx={env['DOCKER_CONTEXT']}]"
    typer.echo(f"+ {' '.join(cmd)}{suffix}")

    merged_env = {**os.environ, **env} if env else None
    return subprocess.run(cmd, text=True, capture_output=True, env=merged_env)


def fail(message: str) -> NoReturn:
    """Print an error message and exit with code 1."""
    typer.echo(f"ERROR: {message}", err=True)
    raise typer.Exit(code=1)


def run_or_fail(
    cmd: list[str], error_msg: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a command; call fail() with error_msg + stderr if it exits non-zero."""
    result = run(cmd, env=env)
    if result.returncode != 0:
        fail(f"{error_msg}:\n{result.stderr}")
    return result


def check(label: str, ok: bool) -> bool:
    """Print a [OK] / [FAIL] status line and return the ok value."""
    status = "[OK]  " if ok else "[FAIL]"
    typer.echo(f"  {status} {label}")
    return ok
