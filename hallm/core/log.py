"""Structured logger factory for hallm.

``get_logger(name)`` returns a Python Logger whose records propagate to:
  - Console (StreamHandler on the root logger, configured via basicConfig).
  - SigNoz via the OTLP LoggingHandler added to root by ``init_observability()``.
  - Glitchtip via the Sentry LoggingIntegration added by ``_init_sentry()``
    (WARNING+ become breadcrumbs, ERROR+ become events).

Call ``init_observability()`` before the first log emission in production so
the OTEL and Sentry pipelines are active.  In tests the plain StreamHandler is
sufficient and no backend wiring is required.
"""

import logging
import sys

from hallm.core.settings import settings

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    stream=sys.stderr,
)


def get_logger(name: str) -> logging.Logger:
    """Return a configured Logger for *name*.

    Level is DEBUG when ``settings.debug`` is true, INFO otherwise.  Records
    propagate to the root logger which forwards them to all registered handlers.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)
    return logger
