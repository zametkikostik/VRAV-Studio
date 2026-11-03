"""Async-friendly circuit breaker for external APIs.

States: closed → open (after failure_threshold consecutive failures)
        open → half_open (after recovery_timeout)
        half_open → closed on success, open on failure.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger("vrav.circuit")

T = TypeVar("T")


class CircuitOpenError(Exception):
    """Raised when the circuit is open and calls are short-circuited."""

    def __init__(self, provider: str, retry_after: float | None = None):
        self.provider = provider
        self.retry_after = retry_after
        msg = f"Circuit open for provider '{provider}'"
        if retry_after is not None:
            msg += f" (retry after {retry_after:.0f}s)"
        super().__init__(msg)


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    _failures: int = 0
    _state: str = "closed"
    _opened_at: float | None = None

    def _now(self) -> float:
        return time.monotonic()

    def state(self) -> str:
        if self._state == "open" and self._opened_at is not None:
            if self._now() - self._opened_at >= self.recovery_timeout:
                self._state = "half_open"
        return self._state

    def allow_request(self) -> bool:
        st = self.state()
        return st in ("closed", "half_open")

    def retry_after(self) -> float | None:
        if self.state() != "open" or self._opened_at is None:
            return None
        left = self.recovery_timeout - (self._now() - self._opened_at)
        return max(0.0, left)

    def record_success(self) -> None:
        self._failures = 0
        self._state = "closed"
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._state == "half_open" or self._failures >= self.failure_threshold:
            self._state = "open"
            self._opened_at = self._now()
            logger.warning(
                "circuit open name=%s failures=%s threshold=%s",
                self.name,
                self._failures,
                self.failure_threshold,
            )

    async def call(self, factory: Callable[[], Awaitable[T]]) -> T:
        if not self.allow_request():
            raise CircuitOpenError(self.name, retry_after=self.retry_after())
        try:
            result = await factory()
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result

    def reset(self) -> None:
        self._failures = 0
        self._state = "closed"
        self._opened_at = None


xai_breaker = CircuitBreaker("xai", failure_threshold=5, recovery_timeout=60.0)
openrouter_breaker = CircuitBreaker("openrouter", failure_threshold=5, recovery_timeout=60.0)
routerai_breaker = CircuitBreaker("routerai", failure_threshold=5, recovery_timeout=60.0)
stripe_breaker = CircuitBreaker("stripe", failure_threshold=3, recovery_timeout=30.0)
yookassa_breaker = CircuitBreaker("yookassa", failure_threshold=3, recovery_timeout=30.0)

_BREAKERS: dict[str, CircuitBreaker] = {
    "xai": xai_breaker,
    "openrouter": openrouter_breaker,
    "routerai": routerai_breaker,
    "stripe": stripe_breaker,
    "yookassa": yookassa_breaker,
}


def get_breaker(name: str) -> CircuitBreaker:
    if name not in _BREAKERS:
        _BREAKERS[name] = CircuitBreaker(name)
    return _BREAKERS[name]


def reset_all_breakers() -> None:
    for b in _BREAKERS.values():
        b.reset()
