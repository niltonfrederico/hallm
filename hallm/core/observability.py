"""Observability bootstrap: Glitchtip (Sentry SDK) + SigNoz (OpenTelemetry)."""

import sentry_sdk
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from hallm.core.settings import settings

_initialized = False


def init_observability() -> None:
    """Wire up Glitchtip + SigNoz exporters. Idempotent."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    if settings.glitchtip_dsn:
        sentry_sdk.init(
            dsn=settings.glitchtip_dsn,
            environment=settings.environment,
            traces_sample_rate=0.0,
        )

    if settings.otel_endpoint:
        resource = Resource.create({"service.name": settings.otel_service_name})
        provider = TracerProvider(resource=resource)
        exporter_kwargs: dict[str, str] = {"endpoint": settings.otel_endpoint}
        ca_cert = settings.SECRETS_PATH / "cerberus-ca.pem"
        if settings.otel_endpoint.startswith("https://") and ca_cert.exists():
            exporter_kwargs["certificate_file"] = str(ca_cert)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(**exporter_kwargs)))
        trace.set_tracer_provider(provider)
        AsyncPGInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
