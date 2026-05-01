"""Unit tests for hallm.cli.base.poll."""

from unittest.mock import patch

from hallm.cli.base import poll


class TestPollUntil:
    def test_returns_true_when_predicate_true_immediately(self) -> None:
        with patch("hallm.cli.base.poll.time.monotonic", return_value=0):
            assert poll.poll_until(lambda: True, timeout=10) is True

    def test_returns_true_when_predicate_eventually_true(self) -> None:
        calls = iter([False, False, True])
        with (
            patch("hallm.cli.base.poll.time.monotonic", side_effect=[0, 0, 1, 2]),
            patch("hallm.cli.base.poll.time.sleep") as sleep_mock,
        ):
            assert poll.poll_until(lambda: next(calls), timeout=10, interval=0.5) is True
        assert sleep_mock.call_count == 2

    def test_returns_false_on_timeout(self) -> None:
        # monotonic ticks: 0 (compute deadline), 0 (loop check), 11 (loop check exits)
        with (
            patch("hallm.cli.base.poll.time.monotonic", side_effect=[0, 0, 11]),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            assert poll.poll_until(lambda: False, timeout=10) is False

    def test_predicate_exception_propagates(self) -> None:
        def boom() -> bool:
            raise RuntimeError("nope")

        with (
            patch("hallm.cli.base.poll.time.monotonic", return_value=0),
            patch("hallm.cli.base.poll.time.sleep"),
        ):
            try:
                poll.poll_until(boom, timeout=1)
            except RuntimeError as exc:
                assert str(exc) == "nope"
            else:  # pragma: no cover
                raise AssertionError("expected RuntimeError")
