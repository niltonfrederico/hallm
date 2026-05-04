"""Unit tests for hallm.core.observability."""

import importlib
import logging
import sys
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


def test_otel_only_skips_sentry_processor_but_installs_w3c_propagator() -> None:
    with (
        _patch_observability_surface() as _,
        patch.object(settings, "glitchtip_dsn", ""),
        patch.object(settings, "otel_endpoint", "http://otel.test:4317"),
    ):
        observability.init_observability()
        observability.SentrySpanProcessor.assert_not_called()
        # W3C TraceContext propagator must always be installed.
        observability.set_global_textmap.assert_called_once()


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

        # CorrelationId + Batch + Sentry processors all land on the provider.
        provider = observability.TracerProvider.return_value
        assert provider.add_span_processor.call_count == 3

        # Sentry propagator is composed alongside the W3C propagator.
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
    assert "integrations" in kwargs


def test_sentry_init_includes_logging_integration() -> None:
    with (
        patch("sentry_sdk.init") as sentry,
        patch.object(settings, "glitchtip_dsn", "https://dsn.test"),
        patch.object(settings, "otel_endpoint", ""),
    ):
        observability.init_observability()
    from sentry_sdk.integrations.logging import LoggingIntegration

    kwargs = sentry.call_args.kwargs
    integrations = kwargs["integrations"]
    assert any(isinstance(i, LoggingIntegration) for i in integrations)
    assert kwargs["enable_logs"] is True


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
            endpoint="https://otel.hallm.local/v1/traces",
            certificate_file=str(ca_cert),
        )
        observability.OTLPLogExporter.assert_called_once_with(
            endpoint="https://otel.hallm.local/v1/logs",
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
        observability.OTLPSpanExporter.assert_called_once_with(
            endpoint="https://otel.hallm.local/v1/traces"
        )
        observability.OTLPLogExporter.assert_called_once_with(
            endpoint="https://otel.hallm.local/v1/logs"
        )


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


def test_resource_includes_deployment_environment_and_cli_command() -> None:
    with (
        _patch_observability_surface() as _,
        patch.object(settings, "glitchtip_dsn", ""),
        patch.object(settings, "otel_endpoint", "http://otel.test:4317"),
        patch.object(settings, "environment", "cluster"),
        patch.object(sys, "argv", ["hallm", "mcp", "serve"]),
    ):
        observability.init_observability()
        resource = observability.TracerProvider.call_args.kwargs["resource"]
        assert resource.attributes.get("deployment.environment") == "cluster"
        assert resource.attributes.get("cli.command") == "hallm.mcp.serve"


def test_correlation_id_processor_stamps_each_span() -> None:
    proc = observability._CorrelationIdSpanProcessor()
    span = MagicMock()
    proc.on_start(span)
    span.set_attribute.assert_called_once_with("correlation.id", proc._id)


def test_correlation_id_is_stable_across_spans() -> None:
    proc = observability._CorrelationIdSpanProcessor()
    span_a, span_b = MagicMock(), MagicMock()
    proc.on_start(span_a)
    proc.on_start(span_b)
    id_a = span_a.set_attribute.call_args.args[1]
    id_b = span_b.set_attribute.call_args.args[1]
    assert id_a == id_b == proc._id


def test_correlation_id_unique_per_processor_instance() -> None:
    assert (
        observability._CorrelationIdSpanProcessor()._id
        != observability._CorrelationIdSpanProcessor()._id
    )


def test_cli_command_from_argv_derives_dot_path() -> None:
    with patch.object(sys, "argv", ["hallm", "seed", "otel", "--message", "x"]):
        assert observability._cli_command_from_argv() == "hallm.seed.otel"


def test_cli_command_from_argv_no_subcommands() -> None:
    with patch.object(sys, "argv", ["hallm"]):
        assert observability._cli_command_from_argv() == "hallm"


def test_cli_command_from_argv_stops_at_flags() -> None:
    with patch.object(sys, "argv", ["hallm", "--debug", "mcp"]):
        assert observability._cli_command_from_argv() == "hallm"


def test_otel_only_processor_count_is_two() -> None:
    """Without Glitchtip: CorrelationId + Batch (no Sentry)."""
    with (
        _patch_observability_surface() as _,
        patch.object(settings, "glitchtip_dsn", ""),
        patch.object(settings, "otel_endpoint", "http://otel.test:4317"),
    ):
        observability.init_observability()
        provider = observability.TracerProvider.return_value
        assert provider.add_span_processor.call_count == 2
