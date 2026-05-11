"""Database subcommands."""

from pathlib import Path

import typer

from hallm.cli.base import kubectl
from hallm.cli.base.shell import fail
from hallm.cli.base.shell import run
from hallm.cli.base.shell import run_or_fail
from hallm.core.settings import settings

app = typer.Typer(help="Database operations.", no_args_is_help=True)

# Package-data: CLI_PATH is derived from this file's location, always valid.
_BOOTSTRAP_PATH = settings.CLI_PATH / "subcommands" / "_bootstrap"
_CONFIGMAP_NAME = "hallm-bootstrap-sql"
_JOB_NAME = "db-bootstrap"
_NAMESPACE = "default"


def _job_manifest() -> Path:
    """Path to the bootstrap Job manifest — lazy so import doesn't need a repo."""
    return settings.k8s_path / "jobs" / "db-bootstrap.yaml"


def _sync_bootstrap_configmap() -> None:
    """Recreate the ConfigMap that ships *.sql files into the Job.

    The ConfigMap holds non-secret SQL templates only — passwords are
    injected at runtime via env vars from the `hallm-env` Secret.
    """
    sql_files = sorted(_BOOTSTRAP_PATH.glob("*.sql"))
    if not sql_files:
        fail(f"No SQL files found in {_BOOTSTRAP_PATH}.")

    create_cmd = [
        "kubectl",
        "create",
        "configmap",
        _CONFIGMAP_NAME,
        "--namespace",
        _NAMESPACE,
        "--dry-run=client",
        "-o",
        "yaml",
    ]
    for f in sql_files:
        create_cmd += ["--from-file", f"{f.name}={f}"]

    kubectl.apply_from_cmd("hallm-bootstrap-sql configmap", create_cmd)


def _delete_prior_job() -> None:
    """Jobs are immutable on most fields — wipe any prior run first."""
    run(
        [
            "kubectl",
            "delete",
            "job",
            _JOB_NAME,
            "--namespace",
            _NAMESPACE,
            "--ignore-not-found",
        ]
    )


def _run_bootstrap() -> None:
    """Trigger the in-cluster db-bootstrap Job and surface its logs."""
    typer.echo(f"==> Syncing ConfigMap '{_CONFIGMAP_NAME}'...")
    _sync_bootstrap_configmap()

    typer.echo(f"==> Removing any prior '{_JOB_NAME}' Job...")
    _delete_prior_job()

    manifest = _job_manifest()
    typer.echo(f"==> Applying {manifest.relative_to(settings.repo_root)}...")
    kubectl.apply(manifest.read_text(), label=_JOB_NAME)

    typer.echo("==> Waiting for Job to complete...")
    wait_cmd = [
        "kubectl",
        "wait",
        "--for=condition=complete",
        f"job/{_JOB_NAME}",
        "--namespace",
        _NAMESPACE,
        "--timeout=180s",
    ]
    result = run(wait_cmd)

    typer.echo("==> Bootstrap Job logs:")
    run_or_fail(
        [
            "kubectl",
            "logs",
            f"job/{_JOB_NAME}",
            "--namespace",
            _NAMESPACE,
            "--tail=-1",
        ],
        "Failed to read bootstrap Job logs",
        stream=True,
    )

    if result.returncode != 0:
        fail(f"db-bootstrap Job did not complete within timeout (see logs above):\n{result.stderr}")

    typer.echo("\nBootstrap complete.")


@app.command()
def bootstrap() -> None:
    """Bootstrap the database (create roles, databases, and initial grants)."""
    _run_bootstrap()
