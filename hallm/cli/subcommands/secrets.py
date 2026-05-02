"""Kubernetes secrets management for the hallm local dev environment."""

import base64
import re
from pathlib import Path

import typer

from hallm.cli.base import kubectl
from hallm.cli.base.shell import fail as _fail
from hallm.cli.base.shell import run_or_fail as _run_or_fail
from hallm.core.settings import settings

# ---------------------------------------------------------------------------
# Cerberus CA helpers (shared with cluster setup)
# ---------------------------------------------------------------------------

_UNREGISTRY_HOST = "unregistry.hallm.local"


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
    issuer_manifest = (settings.K8S_PATH / "adhoc" / "cerberus-ca-issuer.yaml").read_text()
    kubectl.apply(issuer_manifest, label="Cerberus CA ClusterIssuer")


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


def _configure_docker_registry_cert(pem_path: Path) -> None:
    """Copy the Cerberus CA cert into Docker's certs.d so the rootless daemon trusts the registry."""
    certs_dir = Path.home() / ".config" / "docker" / "certs.d" / _UNREGISTRY_HOST
    certs_dir.mkdir(parents=True, exist_ok=True)
    ca_crt = certs_dir / "ca.crt"
    ca_crt.write_text(pem_path.read_text())
    typer.echo(f"  Docker registry cert → {ca_crt}")


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


@app.command("get-certificate")
def get_certificate() -> None:
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
    _configure_docker_registry_cert(pem_path)
