"""Data seeding commands for the hallm local dev environment."""

import sentry_sdk
import typer
from opentelemetry import _logs
from opentelemetry import trace

from hallm.cli.base.shell import fail as _fail
from hallm.core.log import get_logger
from hallm.core.observability import init_observability
from hallm.core.settings import settings

app = typer.Typer(help="Data seeding operations.", no_args_is_help=True)


@app.command()
def log() -> None:
    logger = get_logger("hallm.seed.log")
    logger.info("This is a test log emitted by `hallm seed log`.")


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
    glitchtip_active = settings.glitchtip_enabled and bool(settings.glitchtip_dsn)
    signoz_active = settings.signoz_enabled and bool(settings.otel_endpoint)
    if not glitchtip_active and not signoz_active:
        _fail(
            "Neither GLITCHTIP nor SIGNOZ is enabled — set GLITCHTIP_ENABLED=true "
            "(plus GLITCHTIP_DSN) or SIGNOZ_ENABLED=true (plus OTEL_ENDPOINT) to send."
        )

    settings.otel_service_name = service_name
    init_observability()

    tracer = trace.get_tracer("hallm.seed.otel")
    logger = get_logger("hallm.seed.otel")

    logger.info("emitting trace+log", extra={"seed.service_name": service_name})
    with tracer.start_as_current_span("hallm.seed.otel") as span:
        span.set_attribute("seed.message", message)
        span.set_attribute("seed.service_name", service_name)
        logger.info(message, extra={"seed.message": message})
        if glitchtip_active:
            sentry_sdk.capture_message(message, level="info")
    logger.info("smoke test complete — check SigNoz and Glitchtip for the new event")

    for provider in (trace.get_tracer_provider(), _logs.get_logger_provider()):
        if hasattr(provider, "force_flush"):
            provider.force_flush()

    if glitchtip_active:
        sentry_sdk.flush(timeout=5.0)
