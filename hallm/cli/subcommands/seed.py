"""Data seeding commands for the hallm local dev environment."""

import logging
import subprocess

import sentry_sdk
import typer
from opentelemetry import _logs
from opentelemetry import trace

from hallm.cli.base.poll import poll_until
from hallm.cli.base.shell import fail as _fail
from hallm.core.observability import init_observability
from hallm.core.settings import settings

app = typer.Typer(help="Data seeding operations.", no_args_is_help=True)

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
    probe = (
        "sqlite3 /config/www/SimpleSettings/database.sqlite "
        '\'SELECT name FROM sqlite_master WHERE type="table" AND name="items";\''
    )

    def _has_items_table() -> bool:
        result = subprocess.run(
            ["kubectl", "exec", "-n", namespace, pod_name, "--", "sh", "-c", probe],
            text=True,
            capture_output=True,
        )
        return result.returncode == 0 and "items" in result.stdout

    return poll_until(_has_items_table, timeout=timeout, interval=3.0)


@app.command()
def heimdall(
    namespace: str = typer.Option(_DEFAULT_NAMESPACE, "--namespace", "-n"),
    timeout: int = typer.Option(120, "--timeout", help="Seconds to wait for Heimdall DB."),
) -> None:
    """Populate Heimdall with hallm-managed apps via sqlite3 INSERT OR IGNORE."""
    typer.echo("==> Locating Heimdall pod...")
    pod_name = _heimdall_pod(namespace)
    if not pod_name:
        _fail("No Heimdall pod found. Apply k8s/heimdall.yaml first.")

    typer.echo(f"==> Waiting up to {timeout}s for Heimdall items table...")
    if not _wait_for_heimdall_db(pod_name, namespace, timeout):
        _fail("Heimdall items table did not appear within timeout.")

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


@app.command()
def otel(
    service_name: str = typer.Option(
        "hallm-seed",
        "--service-name",
        help="service.name resource attribute on the emitted span and log.",
    ),
    message: str = typer.Option(
        "hallm seed otel smoke test",
        "--message",
        help="Message body for both the OTEL log and the Glitchtip event.",
    ),
) -> None:
    """Emit one OTEL trace + log + Glitchtip event so both backends can confirm wiring.

    The trace fans out via SentrySpanProcessor (Glitchtip) + BatchSpanProcessor
    (SigNoz). The log goes through the OTLP log pipeline (SigNoz). The Sentry
    capture_message lands in Glitchtip directly.
    """
    if not settings.glitchtip_dsn and not settings.otel_endpoint:
        _fail("Neither GLITCHTIP_DSN nor OTEL_ENDPOINT is set — nothing to send.")

    settings.otel_service_name = service_name
    init_observability()

    typer.echo(f"==> Emitting trace+log as service.name={service_name!r}...")
    tracer = trace.get_tracer("hallm.seed.otel")
    logger = logging.getLogger("hallm.seed.otel")
    logger.setLevel(logging.INFO)

    with tracer.start_as_current_span("hallm-seed-otel-smoke") as span:
        span.set_attribute("seed.message", message)
        span.set_attribute("seed.service_name", service_name)
        logger.info(message, extra={"seed.message": message})
        if settings.glitchtip_dsn:
            sentry_sdk.capture_message(message, level="info")

    for provider in (trace.get_tracer_provider(), _logs.get_logger_provider()):
        if hasattr(provider, "force_flush"):
            provider.force_flush()

    if settings.glitchtip_dsn:
        sentry_sdk.flush(timeout=5.0)

    typer.echo("Done. Check SigNoz and Glitchtip for the new event.")
