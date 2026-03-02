"""Exponential backoff helper."""
import time
from typing import Callable, TypeVar

from app.utils.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T")


def exponential_backoff(attempt: int, base: float = 60.0, max_wait: float = 300.0) -> float:
    """Return wait seconds for a given attempt (0-indexed)."""
    wait = min(base * (2 ** attempt), max_wait)
    return wait


def retry_with_backoff(
    fn: Callable[[], T],
    max_attempts: int = 3,
    base: float = 2.0,
    exceptions: tuple = (Exception,),
    label: str = "operation",
) -> T:
    """Run *fn* up to *max_attempts* times with exponential backoff.

    Raises the last exception if all attempts fail.
    """
    last_exc: Exception = RuntimeError("No attempts made")
    for attempt in range(max_attempts):
        try:
            return fn()
        except exceptions as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                wait = exponential_backoff(attempt, base=base)
                log.warning(
                    "retry.backoff",
                    label=label,
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                    wait_s=wait,
                    error=str(exc),
                )
                time.sleep(wait)
            else:
                log.error(
                    "retry.exhausted",
                    label=label,
                    attempts=max_attempts,
                    error=str(exc),
                )
    raise last_exc
