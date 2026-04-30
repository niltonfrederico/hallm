"""Low-level shell helpers for CLI subcommands."""

import subprocess

import typer


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a shell command, echoing it first, and return the completed process."""
    typer.echo(f"+ {' '.join(cmd)}")
    return subprocess.run(cmd, text=True, capture_output=True)


def fail(message: str) -> None:
    """Print an error message and exit with code 1."""
    typer.echo(f"ERROR: {message}", err=True)
    raise typer.Exit(code=1)


def check(label: str, ok: bool) -> bool:
    """Print a [OK] / [FAIL] status line and return the ok value."""
    status = "[OK]  " if ok else "[FAIL]"
    typer.echo(f"  {status} {label}")
    return ok
