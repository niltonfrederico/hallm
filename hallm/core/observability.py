"""Observability bootstrap: Glitchtip (Sentry SDK) + SigNoz (OpenTelemetry).

When both backends are configured, OTEL spans are fanned out to **both**:
  - SigNoz, via the OTLP HTTP exporter on a BatchSpanProcessor.
  - Glitchtip, via sentry-sdk's SentrySpanProcessor (which serialises spans
    into the Sentry envelope protocol).

The SentryPropagator becomes the global text map so trace context survives
across HTTP boundaries between hallm services and either backend.
"""

import logging

import sentry_sdk
from opentelemetry import _logs
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.starlette import StarletteInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs import LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sentry_sdk.integrations.opentelemetry import SentryPropagator
from sentry_sdk.integrations.opentelemetry import SentrySpanProcessor

from hallm.core.settings import settings

_initialized = False


def _init_sentry(*, otel_enabled: bool) -> None:
    """Initialise the Sentry SDK pointing at Glitchtip.

    When OTEL is also enabled we hand performance instrumentation over to
    OTEL (``instrumenter="otel"``) so spans aren't double-counted, and bump
    ``traces_sample_rate`` so the SentrySpanProcessor isn't dropped on the
    floor.
    """
    init_kwargs: dict[str, object] = {
        "dsn": settings.glitchtip_dsn,
        "environment": settings.environment,
    }
    if otel_enabled:
        init_kwargs["instrumenter"] = "otel"
        init_kwargs["traces_sample_rate"] = settings.sentry_traces_sample_rate
    else:
        init_kwargs["traces_sample_rate"] = 0.0
    ca_cert = settings.SECRETS_PATH / "cerberus-ca.pem"
    if ca_cert.exists():
        init_kwargs["ca_certs"] = str(ca_cert)
    sentry_sdk.init(**init_kwargs)


def _otlp_exporter_kwargs(signal_path: str) -> dict[str, str]:
    """Shared kwargs for OTLP HTTP exporters: endpoint + Cerberus CA if HTTPS.

    The SDK (>=1.12) does NOT auto-append signal paths to custom endpoints,
    so callers must pass the correct path (e.g. "v1/traces", "v1/logs").
    """
    base = settings.otel_endpoint.rstrip("/")
    kwargs: dict[str, str] = {"endpoint": f"{base}/{signal_path}"}
    ca_cert = settings.SECRETS_PATH / "cerberus-ca.pem"
    if base.startswith("https://") and ca_cert.exists():
        kwargs["certificate_file"] = str(ca_cert)
    return kwargs


def _build_otlp_exporter() -> OTLPSpanExporter:
    return OTLPSpanExporter(**_otlp_exporter_kwargs("v1/traces"))


def _build_otlp_log_exporter() -> OTLPLogExporter:
    return OTLPLogExporter(**_otlp_exporter_kwargs("v1/logs"))


def _instrument_libraries() -> None:
    """Patch every third-party library hallm uses for outbound I/O.

    Patching is global and idempotent within a process; safe to call once at
    boot. Each instrumentor wraps spans in the active TracerProvider.
    """
    AsyncPGInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    RedisInstrumentor().instrument()
    BotocoreInstrumentor().instrument()
    StarletteInstrumentor().instrument()
    # set_logging_format=False keeps us from clobbering the user's log config;
    # we only want the trace_id/span_id attributes injected on records.
    LoggingInstrumentor().instrument(set_logging_format=False)


def init_observability() -> None:
    """Wire up Glitchtip + SigNoz exporters and instrument libraries. Idempotent."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    glitchtip_enabled = bool(settings.glitchtip_dsn)
    otel_enabled = bool(settings.otel_endpoint)

    if glitchtip_enabled:
        _init_sentry(otel_enabled=otel_enabled)

    if not otel_enabled:
        return

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(_build_otlp_exporter()))
    if glitchtip_enabled:
        provider.add_span_processor(SentrySpanProcessor())
        set_global_textmap(SentryPropagator())
    trace.set_tracer_provider(provider)

    log_provider = LoggerProvider(resource=resource)
    log_provider.add_log_record_processor(BatchLogRecordProcessor(_build_otlp_log_exporter()))
    _logs.set_logger_provider(log_provider)
    logging.getLogger().addHandler(LoggingHandler(level=logging.INFO, logger_provider=log_provider))

    _instrument_libraries()
