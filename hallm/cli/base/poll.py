"""Generic polling helper for waiting on async/external state."""

import time
from collections.abc import Callable


def poll_until(
    predicate: Callable[[], bool],
    *,
    timeout: float,
    interval: float = 2.0,
) -> bool:
    """Call ``predicate`` repeatedly until it returns truthy or ``timeout`` elapses.

    Returns ``True`` if the predicate succeeded, ``False`` if the deadline was
    reached. ``time.monotonic`` is used for the deadline; tests can patch it
    plus ``time.sleep`` to drive deterministic iterations.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False
