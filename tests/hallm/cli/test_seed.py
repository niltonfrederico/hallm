"""Unit tests for hallm.cli.subcommands.seed."""

from unittest.mock import MagicMock
from unittest.mock import patch

from typer.testing import CliRunner

from hallm.cli.subcommands.seed import app
from hallm.core.settings import settings


class TestOtel:
    def test_aborts_when_neither_backend_configured(self, runner: CliRunner) -> None:
        with (
            patch.object(settings, "glitchtip_dsn", ""),
            patch.object(settings, "otel_endpoint", ""),
        ):
            result = runner.invoke(app, ["otel"])
        assert result.exit_code == 1
        assert "nothing to send" in result.output

    def test_emits_span_log_and_glitchtip_event(self, runner: CliRunner) -> None:
        tracer = MagicMock()
        provider = MagicMock(spec=["force_flush"])
        log_provider = MagicMock(spec=["force_flush"])
        with (
            patch.object(settings, "glitchtip_dsn", "https://dsn.test"),
            patch.object(settings, "otel_endpoint", "http://otel.test:4317"),
            patch("hallm.cli.subcommands.seed.init_observability") as init_obs,
            patch("hallm.cli.subcommands.seed.trace.get_tracer", return_value=tracer),
            patch("hallm.cli.subcommands.seed.trace.get_tracer_provider", return_value=provider),
            patch(
                "hallm.cli.subcommands.seed._logs.get_logger_provider",
                return_value=log_provider,
            ),
            patch("hallm.cli.subcommands.seed.sentry_sdk.capture_message") as capture,
            patch("hallm.cli.subcommands.seed.sentry_sdk.flush") as flush,
        ):
            result = runner.invoke(app, ["otel", "--service-name", "x", "--message", "hello"])

        assert result.exit_code == 0, result.output
        init_obs.assert_called_once()
        tracer.start_as_current_span.assert_called_once_with("hallm.seed.otel")
        capture.assert_called_once_with("hello", level="info")
        provider.force_flush.assert_called_once()
        log_provider.force_flush.assert_called_once()
        flush.assert_called_once_with(timeout=5.0)
        assert settings.otel_service_name == "x"

    def test_skips_glitchtip_when_dsn_blank(self, runner: CliRunner) -> None:
        tracer = MagicMock()
        with (
            patch.object(settings, "glitchtip_dsn", ""),
            patch.object(settings, "otel_endpoint", "http://otel.test:4317"),
            patch("hallm.cli.subcommands.seed.init_observability"),
            patch("hallm.cli.subcommands.seed.trace.get_tracer", return_value=tracer),
            patch(
                "hallm.cli.subcommands.seed.trace.get_tracer_provider",
                return_value=MagicMock(spec=[]),
            ),
            patch(
                "hallm.cli.subcommands.seed._logs.get_logger_provider",
                return_value=MagicMock(spec=[]),
            ),
            patch("hallm.cli.subcommands.seed.sentry_sdk.capture_message") as capture,
        ):
            result = runner.invoke(app, ["otel"])

        assert result.exit_code == 0, result.output
        capture.assert_not_called()
