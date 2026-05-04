"""Unit tests for hallm.core.observability."""

import importlib
import logging
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from hallm.core import observability
from hallm.core.settings import settings

# Every external surface init_observability touches; patched as a bundle so
# tests can assert which were called without recreating the boilerplate.
_INSTRUMENTOR_PATHS = (
    "AsyncPGInstrumentor",
    "HTTPXClientInstrumentor",
    "RedisInstrumentor",
    "BotocoreInstrumentor",
    "StarletteInstrumentor",
    "LoggingInstrumentor",
)


@pytest.fixture(autouse=True)
def _reset_initialised() -> None:
    """Reset the module-level guard and root logger handlers between tests.

    init_observability() attaches a LoggingHandler to the root logger; under
    `_patch_observability_surface()` that handler is a MagicMock. Without
    cleanup it leaks into other tests and breaks any logging.* call.
    """
    root = logging.getLogger()
    snapshot = list(root.handlers)
    importlib.reload(observability)
    yield
    root.handlers = snapshot


def _patch_observability_surface() -> ExitStack:
    """Patch every external collaborator and return the open ExitStack.

    The caller can pull mocks out of the stack via ``stack.enter_context``
    or look them up by attribute on the module after entering.
    """
    stack = ExitStack()
    stack.enter_context(patch("hallm.core.observability.OTLPSpanExporter"))
    stack.enter_context(patch("hallm.core.observability.OTLPLogExporter"))
    stack.enter_context(patch("hallm.core.observability.TracerProvider", return_value=MagicMock()))
    stack.enter_context(patch("hallm.core.observability.LoggerProvider", return_value=MagicMock()))
    stack.enter_context(patch("hallm.core.observability.LoggingHandler"))
    stack.enter_context(patch("hallm.core.observability.BatchLogRecordProcessor"))
    stack.enter_context(patch("hallm.core.observability.trace.set_tracer_provider"))
    stack.enter_context(patch("hallm.core.observability._logs.set_logger_provider"))
    stack.enter_context(patch("hallm.core.observability.set_global_textmap"))
    stack.enter_context(patch("hallm.core.observability.SentrySpanProcessor"))
    for name in _INSTRUMENTOR_PATHS:
        stack.enter_context(patch(f"hallm.core.observability.{name}"))
    return stack


def test_init_observability_idempotent() -> None:
    with (
        patch("sentry_sdk.init") as sentry,
        patch.object(settings, "glitchtip_dsn", "https://dsn.test"),
        patch.object(settings, "otel_endpoint", ""),
    ):
        observability.init_observability()
        observability.init_observability()
        sentry.assert_called_once()


def test_otel_only_skips_sentry_processor_and_propagator() -> None:
    with (
        _patch_observability_surface() as _,
        patch.object(settings, "glitchtip_dsn", ""),
        patch.object(settings, "otel_endpoint", "http://otel.test:4317"),
    ):
        observability.init_observability()
        # Without a DSN, no Sentry processor and no Sentry propagator.
        observability.SentrySpanProcessor.assert_not_called()
        observability.set_global_textmap.assert_not_called()


def test_otel_only_instruments_every_library() -> None:
    with (
        _patch_observability_surface() as _,
        patch.object(settings, "glitchtip_dsn", ""),
        patch.object(settings, "otel_endpoint", "http://otel.test:4317"),
    ):
        observability.init_observability()
        for name in _INSTRUMENTOR_PATHS:
            getattr(observability, name).return_value.instrument.assert_called_once()


def test_logging_instrumentor_does_not_overwrite_format() -> None:
    """LoggingInstrumentor must be called with set_logging_format=False so it
    only injects trace_id/span_id without rewriting log formatters."""
    with (
        _patch_observability_surface() as _,
        patch.object(settings, "glitchtip_dsn", ""),
        patch.object(settings, "otel_endpoint", "http://otel.test:4317"),
    ):
        observability.init_observability()
        observability.LoggingInstrumentor.return_value.instrument.assert_called_once_with(
            set_logging_format=False
        )


def test_glitchtip_plus_otel_fans_out_to_both_processors() -> None:
    with (
        _patch_observability_surface() as _,
        patch("sentry_sdk.init") as sentry,
        patch.object(settings, "glitchtip_dsn", "https://dsn.test"),
        patch.object(settings, "otel_endpoint", "http://otel.test:4317"),
        patch.object(settings, "sentry_traces_sample_rate", 0.5),
    ):
        observability.init_observability()

        sentry.assert_called_once()
        kwargs = sentry.call_args.kwargs
        assert kwargs["dsn"] == "https://dsn.test"
        assert kwargs["instrumenter"] == "otel"
        assert kwargs["traces_sample_rate"] == 0.5

        # Both span processors land on the provider.
        provider = observability.TracerProvider.return_value
        assert provider.add_span_processor.call_count == 2

        # And the Sentry propagator is installed globally so trace context
        # survives across HTTP boundaries between SigNoz and Glitchtip.
        observability.set_global_textmap.assert_called_once()


def test_glitchtip_only_init_uses_zero_traces_sample_rate() -> None:
    """Without OTEL the Sentry init must not enable performance tracing."""
    with (
        patch("sentry_sdk.init") as sentry,
        patch.object(settings, "glitchtip_dsn", "https://dsn.test"),
        patch.object(settings, "otel_endpoint", ""),
    ):
        observability.init_observability()
    kwargs = sentry.call_args.kwargs
    assert kwargs["traces_sample_rate"] == 0.0
    assert "instrumenter" not in kwargs


def test_https_endpoint_with_cert(tmp_path: Path) -> None:
    ca_cert = tmp_path / "cerberus-ca.pem"
    ca_cert.write_text("CERT")
    with (
        _patch_observability_surface() as _,
        patch.object(settings, "glitchtip_dsn", ""),
        patch.object(settings, "otel_endpoint", "https://otel.hallm.local"),
        patch.object(settings, "SECRETS_PATH", tmp_path),
    ):
        observability.init_observability()
        observability.OTLPSpanExporter.assert_called_once_with(
            endpoint="https://otel.hallm.local",
            certificate_file=str(ca_cert),
        )
        observability.OTLPLogExporter.assert_called_once_with(
            endpoint="https://otel.hallm.local",
            certificate_file=str(ca_cert),
        )


def test_https_endpoint_without_cert(tmp_path: Path) -> None:
    with (
        _patch_observability_surface() as _,
        patch.object(settings, "glitchtip_dsn", ""),
        patch.object(settings, "otel_endpoint", "https://otel.hallm.local"),
        patch.object(settings, "SECRETS_PATH", tmp_path),
    ):
        observability.init_observability()
        observability.OTLPSpanExporter.assert_called_once_with(endpoint="https://otel.hallm.local")
        observability.OTLPLogExporter.assert_called_once_with(endpoint="https://otel.hallm.local")


def test_otel_log_provider_wired_with_batch_processor() -> None:
    with (
        _patch_observability_surface() as _,
        patch.object(settings, "glitchtip_dsn", ""),
        patch.object(settings, "otel_endpoint", "http://otel.test:4317"),
    ):
        observability.init_observability()
        log_provider = observability.LoggerProvider.return_value
        log_provider.add_log_record_processor.assert_called_once()
        observability._logs.set_logger_provider.assert_called_once_with(log_provider)
        observability.LoggingHandler.assert_called_once()


def test_no_dsn_no_endpoint_does_nothing() -> None:
    with (
        patch("sentry_sdk.init") as sentry,
        patch.object(settings, "glitchtip_dsn", ""),
        patch.object(settings, "otel_endpoint", ""),
    ):
        observability.init_observability()
        sentry.assert_not_called()
