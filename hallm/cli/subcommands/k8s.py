"""Kubernetes operations for the hallm local dev environment."""

import subprocess
import time

import typer

from hallm.cli.base import kubectl
from hallm.cli.base.shell import fail as _fail
from hallm.core.settings import settings

app = typer.Typer(help="Kubernetes operations.")

_DEFAULT_NAMESPACE = "default"

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


@app.command("sync-secrets")
def sync_secrets() -> None:
    """Sync .env → Secret 'hallm-env' in the cluster."""
    env_path = settings.ROOT_PATH / ".env"

    if not env_path.exists():
        _fail(f".env not found at {env_path}")

    typer.echo("==> Syncing .env → Secret 'hallm-env'...")
    kubectl.apply_from_cmd(
        "Secret 'hallm-env'",
        [
            "kubectl",
            "create",
            "secret",
            "generic",
            "hallm-env",
            f"--from-env-file={env_path}",
            "--dry-run=client",
            "-o",
            "yaml",
        ],
    )

    typer.echo("\nDone.")


@app.command()
def remove(
    name: str = typer.Argument(
        ..., help="Manifest name in k3d/ (without .yaml), e.g. 'ollama', 'postgres'"
    ),
    namespace: str = typer.Option(
        _DEFAULT_NAMESPACE, "--namespace", "-n", help="Kubernetes namespace"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Remove a deployment and all associated resources (volumes, secrets, configmaps, ingresses).

    Deletes everything defined in k3d/<name>.yaml, then sweeps for any PVCs, Secrets,
    and ConfigMaps labelled app=<name> in the target namespace.
    """
    manifest = settings.K3D_PATH / f"{name}.yaml"
    if not manifest.exists():
        _fail(
            f"No manifest found at {manifest}. "
            f"Available manifests: {', '.join(p.stem for p in settings.K3D_PATH.glob('*.yaml'))}"
        )

    # Collect the resource types to sweep by label after manifest deletion.
    _SWEEP_KINDS = ["persistentvolumeclaims", "secrets", "configmaps", "ingresses"]

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
    for kind in _SWEEP_KINDS:
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
        for kind in _SWEEP_KINDS:
            kubectl.delete_by_label(kind, f"app={name}", namespace=namespace)

    typer.echo(f"\nDone. '{name}' and associated resources removed.")


@app.command("seed-heimdall")
def seed_heimdall(
    namespace: str = typer.Option(_DEFAULT_NAMESPACE, "--namespace", "-n"),
    timeout: int = typer.Option(120, "--timeout", help="Seconds to wait for Heimdall DB"),
) -> None:
    """Populate Heimdall with hallm-managed apps via sqlite3 INSERT OR IGNORE.

    Heimdall stores apps in /config/www/SimpleSettings/database.sqlite. The DB
    is created by Laravel migrations on first start, so we poll until the
    `items` table exists, then seed.
    """
    typer.echo("==> Locating Heimdall pod...")
    pod_name = _heimdall_pod(namespace)
    if not pod_name:
        _fail("No Heimdall pod found. Apply k3d/heimdall.yaml first.")
        return

    typer.echo(f"==> Waiting up to {timeout}s for Heimdall items table...")
    if not _wait_for_heimdall_db(pod_name, namespace, timeout):
        _fail("Heimdall items table did not appear within timeout.")
        return

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
    deadline = time.monotonic() + timeout
    probe = (
        "sqlite3 /config/www/SimpleSettings/database.sqlite "
        '\'SELECT name FROM sqlite_master WHERE type="table" AND name="items";\''
    )
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["kubectl", "exec", "-n", namespace, pod_name, "--", "sh", "-c", probe],
            text=True,
            capture_output=True,
        )
        if result.returncode == 0 and "items" in result.stdout:
            return True
        time.sleep(3)
    return False
