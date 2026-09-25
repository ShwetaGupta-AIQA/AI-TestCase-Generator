"""Request-scoped demo limits; durable workflows have no demo policy."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Lock
import time

MAX_UPLOAD_BYTES = 4_000_000
MAX_TEXT_CHARS = 12_000
MAX_DOCUMENT_CHARS = 30_000
MAX_RESPONSE_BYTES = 4_000_000
MAX_SCENARIOS = 3
MAX_CASES = 3
DEADLINE_SECONDS = 240


class DemoLimitError(ValueError):
    pass


class DemoTimeoutError(TimeoutError):
    pass


@dataclass
class Budget:
    deadline: float
    calls: int = 0
    lock: Lock = field(default_factory=Lock)


_budget = ContextVar("demo_budget", default=None)


def active():
    return _budget.get() is not None


def remaining():
    budget = _budget.get()
    if budget is None:
        return 60.0
    seconds = budget.deadline - time.monotonic()
    if seconds <= 0:
        raise DemoTimeoutError("Demo generation timed out. Try a shorter requirement.")
    return seconds


def before_call():
    remaining()
    budget = _budget.get()
    if budget is not None:
        with budget.lock:
            if budget.calls >= 12:
                raise DemoLimitError("Demo model-call limit reached. Try a simpler requirement.")
            budget.calls += 1


@contextmanager
def demo_budget():
    token = _budget.set(Budget(time.monotonic() + DEADLINE_SECONDS))
    try:
        yield
        remaining()
    finally:
        _budget.reset(token)
