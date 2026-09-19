"""A circuit breaker: closed, open, half-open (T6.7 piece 5).

## What a breaker is that a retry is not

`Resilient` retries one call. It keeps no state between calls, so the tenth model call of a run
against a provider that has been down since the first spends the same four attempts and the same
backoff as the first did - forty attempts and several minutes of a run's budget to learn one fact
ten times. Tools have no retry at all, and a specialist with twelve calls against a Loki that is
down spends twelve `HTTP_TIMEOUT`s to learn the same fact twelve times. A breaker is the memory:
after `threshold` consecutive failures it **opens**, and while open every call is refused at
once, without contacting anything; after `cooldown` seconds it **half-opens** and lets exactly
one call through as a trial - success closes it, failure re-opens it for another cooldown.

## What counts as a failure is the caller's business

The breaker counts what it is told. For the provider, a failure is one *exhausted retry
schedule* - `Resilient` has already spent its attempts, so one exhaustion is evidence enough and
the threshold is 1. For a tool backend, a failure is one call that raised, and the threshold is 3:
a single Loki timeout is weather, three in a row is a backend that is down. Neither the provider
nor the tools decide what their threshold is here; `AgentSettings` and `ToolSettings` do.

## Where the state lives

In the process. A `faultline-investigate` run is one process, so a breaker here bounds what one
run can spend on a dead dependency; across runs, the orchestrator's runner reads the *record* -
the last trajectories' outcomes - rather than a second store (`orchestrator.runner`). Nothing is
persisted by this module, deliberately: a persisted breaker is a second source of truth about the
provider's health beside the trajectory table, and the two would disagree eventually.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """The call was refused without being attempted, because the breaker is open."""

    def __init__(self, name: str, seconds_until_trial: float) -> None:
        self.name = name
        self.seconds_until_trial = seconds_until_trial
        super().__init__(
            f"{name}: circuit open, not attempted; a trial call is allowed in "
            f"{seconds_until_trial:.0f}s"
        )


class CircuitBreaker:
    """One dependency's state. Not thread-safe by design: `Resilient` and `Tools` are used from
    one investigation's threads through `propagate`, and a race here costs at most one extra trial
    call, which is the price a breaker exists to make small."""

    def __init__(
        self,
        name: str,
        *,
        threshold: int,
        cooldown_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self.threshold = max(1, threshold)
        self.cooldown = cooldown_seconds
        self._clock = clock
        self._consecutive = 0
        self._opened_at: float | None = None
        self._trial_in_flight = False
        self.trips = 0
        """How many times this breaker has opened. For the record, and for tests."""

    @property
    def state(self) -> BreakerState:
        if self._opened_at is None:
            return BreakerState.CLOSED
        if self._clock() - self._opened_at >= self.cooldown:
            return BreakerState.HALF_OPEN
        return BreakerState.OPEN

    def seconds_until_trial(self) -> float:
        if self._opened_at is None:
            return 0.0
        return max(0.0, self.cooldown - (self._clock() - self._opened_at))

    def allow(self) -> None:
        """Raise `CircuitOpenError` unless a call may proceed. In half-open, exactly one may."""
        state = self.state
        if state is BreakerState.CLOSED:
            return
        if state is BreakerState.HALF_OPEN and not self._trial_in_flight:
            self._trial_in_flight = True
            return
        raise CircuitOpenError(self.name, self.seconds_until_trial())

    def record_success(self) -> None:
        self._consecutive = 0
        self._opened_at = None
        self._trial_in_flight = False

    def record_failure(self) -> None:
        self._consecutive += 1
        self._trial_in_flight = False
        if self._opened_at is not None or self._consecutive >= self.threshold:
            # Open (or re-open after a failed trial): the cooldown starts again from now.
            if self._opened_at is None:
                self.trips += 1
            self._opened_at = self._clock()
            self._consecutive = 0

    def call[T](self, fn: Callable[[], T]) -> T:
        """`allow`, then `fn`, recording the outcome. The exception from `fn` propagates as it
        is - the breaker counts it and does not swallow it."""
        self.allow()
        try:
            result = fn()
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result
