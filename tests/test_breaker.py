"""`reliability.breaker` (T6.7 piece 5): closed, open, half-open, and what each does to a call.

The two users are `agents.model.Resilient` (threshold 1 per model: an exhausted retry schedule is
evidence enough) and `tools.tools.Tools` (threshold 3 per backend, no half-open inside a run).
Their tests are beside them; this file holds the primitive to its own words.
"""

from __future__ import annotations

import pytest

from faultline.reliability.breaker import BreakerState, CircuitBreaker, CircuitOpenError


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _breaker(threshold: int = 3, cooldown: float = 60.0) -> tuple[CircuitBreaker, Clock]:
    clock = Clock()
    breaker = CircuitBreaker("loki", threshold=threshold, cooldown_seconds=cooldown, clock=clock)
    return breaker, clock


def test_closed_until_threshold_consecutive_failures_then_open() -> None:
    breaker, _ = _breaker(threshold=3)

    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state is BreakerState.CLOSED, "two is not three"
    breaker.record_success()
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state is BreakerState.CLOSED, "a success resets the count - consecutive"
    breaker.record_failure()

    assert breaker.state is BreakerState.OPEN
    assert breaker.trips == 1
    with pytest.raises(CircuitOpenError, match="loki: circuit open"):
        breaker.allow()


def test_open_refuses_without_calling_and_half_opens_after_the_cooldown() -> None:
    breaker, clock = _breaker(threshold=1, cooldown=60.0)
    calls = 0

    def fn() -> str:
        nonlocal calls
        calls += 1
        raise TimeoutError("no answer")

    with pytest.raises(TimeoutError):
        breaker.call(fn)
    assert breaker.state is BreakerState.OPEN and calls == 1
    with pytest.raises(CircuitOpenError):
        breaker.call(fn)
    assert calls == 1, "open: the function was not called"
    assert 0 < breaker.seconds_until_trial() <= 60

    clock.now += 60
    assert breaker.state is BreakerState.HALF_OPEN
    assert breaker.seconds_until_trial() == 0


def test_half_open_lets_exactly_one_trial_through_and_a_success_closes_it() -> None:
    breaker, clock = _breaker(threshold=1, cooldown=10.0)
    breaker.record_failure()
    clock.now += 10

    breaker.allow()  # the trial
    with pytest.raises(CircuitOpenError):
        breaker.allow()  # a second caller while the trial is in flight
    breaker.record_success()

    assert breaker.state is BreakerState.CLOSED
    breaker.allow()


def test_a_failed_trial_reopens_for_another_cooldown() -> None:
    breaker, clock = _breaker(threshold=1, cooldown=10.0)
    breaker.record_failure()
    clock.now += 10
    breaker.allow()
    breaker.record_failure()

    assert breaker.state is BreakerState.OPEN
    assert breaker.trips == 1, "a re-open after a failed trial is the same outage, not a new trip"
    assert breaker.seconds_until_trial() == 10.0


def test_an_infinite_cooldown_never_half_opens() -> None:
    """The tools' breakers: open for the rest of the run."""
    breaker, clock = _breaker(threshold=1, cooldown=float("inf"))
    breaker.record_failure()
    clock.now += 1e9

    assert breaker.state is BreakerState.OPEN
    with pytest.raises(CircuitOpenError):
        breaker.allow()


def test_call_records_the_outcome_and_lets_the_exception_through_unchanged() -> None:
    breaker, _ = _breaker(threshold=2)

    assert breaker.call(lambda: "fine") == "fine"

    def boom() -> None:
        raise ValueError("their words")

    with pytest.raises(ValueError, match="their words"):
        breaker.call(boom)
    assert breaker.state is BreakerState.CLOSED, "one of two"
