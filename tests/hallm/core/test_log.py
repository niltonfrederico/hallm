"""Unit tests for hallm.core.log."""

import logging
from unittest.mock import patch

from hallm.core import log
from hallm.core.settings import settings


def test_get_logger_returns_named_logger() -> None:
    logger = log.get_logger("hallm.test.named")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "hallm.test.named"


def test_get_logger_level_info_when_not_debug() -> None:
    with patch.object(settings, "debug", False):
        logger = log.get_logger("hallm.test.info_level")
    assert logger.level == logging.INFO


def test_get_logger_level_debug_when_debug_on() -> None:
    with patch.object(settings, "debug", True):
        logger = log.get_logger("hallm.test.debug_level")
    assert logger.level == logging.DEBUG


def test_get_logger_propagates_to_root() -> None:
    logger = log.get_logger("hallm.test.propagates")
    assert logger.propagate is True


def test_root_logger_has_stream_handler_after_import() -> None:
    root = logging.getLogger()
    stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
    assert stream_handlers, "basicConfig should have added a StreamHandler to root"
