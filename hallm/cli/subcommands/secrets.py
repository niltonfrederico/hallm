"""Kubernetes secrets management for the hallm local dev environment."""

import re
from pathlib import Path

import typer

from hallm.cli.base import kubectl
from hallm.cli.base.shell import fail as _fail
from hallm.core.settings import settings

app = typer.Typer(help="Kubernetes secrets management.", no_args_is_help=True)

# Replaces https?://name.hallm.local with http://name.default.svc.cluster.local,
# then bare hostnames name.hallm.local with name.default.svc.cluster.local.
_URL_RE = re.compile(r"https?://([a-z0-9-]+)\.hallm\.local")
_HOST_RE = re.compile(r"([a-z0-9-]+)\.hallm\.local")
_ENV_RE = re.compile(r"^(ENVIRONMENT=).*$", re.MULTILINE)


def _sync_secrets() -> None:
    """Sync ~/.hallm/*.env files → Kubernetes Secrets (shared with k8s setup)."""
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
def apply() -> None:
    """Sync ~/.hallm/*.env files → Kubernetes Secrets.

    Each <secret-name>.env file in ~/.hallm/ is applied as a Secret named
    <secret-name>.  A file named exactly .env is applied as 'hallm-env'.
    """
    _sync_secrets()


@app.command()
def prepare() -> None:
    """Rewrite workspace .env for in-cluster use and save it to ~/.hallm/.env.

    Reads the project's .env, rewrites every *.hallm.local address to its
    Kubernetes service equivalent (*.default.svc.cluster.local), strips TLS
    from those internal URLs, and sets ENVIRONMENT=kubernetes so the app uses
    the cluster-internal database host.  The result is written to ~/.hallm/.env
    so that `hallm secrets apply` picks it up as the 'hallm-env' Secret.
    """
    src = settings.ROOT_PATH / ".env"
    if not src.exists():
        _fail(f"No .env found at {src}")

    dest = settings.SECRETS_PATH / ".env"
    settings.SECRETS_PATH.mkdir(parents=True, exist_ok=True)

    text = src.read_text()

    text = _URL_RE.sub(r"http://\1.default.svc.cluster.local", text)
    text = _HOST_RE.sub(r"\1.default.svc.cluster.local", text)
    text = _ENV_RE.sub(r"\1kubernetes", text)

    dest.write_text(text)
    typer.echo(f"  {src} → {dest}")
    typer.echo("Done.")
