"""Unit tests for hallm.core.observability."""

import importlib
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from hallm.core import observability
from hallm.core.settings import settings


@pytest.fixture(autouse=True)
def _reset_initialised() -> None:
    """Reset the module-level guard so each test starts fresh."""
    importlib.reload(observability)


def test_init_observability_idempotent() -> None:
    with (
        patch("sentry_sdk.init") as sentry,
        patch.object(settings, "glitchtip_dsn", "https://dsn.test"),
        patch.object(settings, "otel_endpoint", ""),
    ):
        observability.init_observability()
        observability.init_observability()
        sentry.assert_called_once()


def test_init_observability_sets_up_otel_when_endpoint_set() -> None:
    with (
        patch.object(settings, "glitchtip_dsn", ""),
        patch.object(settings, "otel_endpoint", "http://otel.test:4317"),
        patch("hallm.core.observability.OTLPSpanExporter"),
        patch("hallm.core.observability.TracerProvider", return_value=MagicMock()),
        patch("hallm.core.observability.trace.set_tracer_provider"),
        patch("hallm.core.observability.AsyncPGInstrumentor") as asyncpg_inst,
        patch("hallm.core.observability.HTTPXClientInstrumentor") as httpx_inst,
    ):
        observability.init_observability()
        asyncpg_inst.return_value.instrument.assert_called_once()
        httpx_inst.return_value.instrument.assert_called_once()


def test_init_observability_no_dsn_no_endpoint() -> None:
    with (
        patch("sentry_sdk.init") as sentry,
        patch.object(settings, "glitchtip_dsn", ""),
        patch.object(settings, "otel_endpoint", ""),
    ):
        observability.init_observability()
        sentry.assert_not_called()
