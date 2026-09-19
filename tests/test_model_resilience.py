"""Retrying, substituting, and the difference between them (T2.5, ADR-0031).

A retry changes nothing anything records: the same model answered. A substitution changes
which model answered, and `freeze.model_map()` records the model a run was *configured* with
— so a silent fallback would leave the freeze asserting a model that never ran. These tests
pin both halves: that transient failures are retried, and that a substitution is never quiet.
"""

from __future__ import annotations

from typing import Any

import pytest

from faultline.agents.model import ModelRequest, ModelResponse, Resilient, is_transient
from faultline.agents.settings import AgentSettings

REQUEST = ModelRequest(system="s", messages=[{"role": "user", "content": "hi"}], role="planner")


class _OverloadedError(Exception):
    """Anthropic's 529 - the one that ended a registered run at T7.58."""

    status_code = 529


class _BadRequestError(Exception):
    """A request that will fail identically however many times it is sent."""

    status_code = 400


class APIConnectionError(Exception):
    """Carries no status code, so it is classified by name.

    Named exactly as the SDK names it, deliberately. `is_transient` matches
    `type(exc).__name__`, so a stub called `_APIConnectionError` would not match and would
    prove nothing about the real one - which is how this test first failed.
    """


class _Stub:
    """Fails a set number of times, then answers."""

    def __init__(
        self, name: str, failures: int = 0, error: type[Exception] = _OverloadedError
    ) -> None:
        self._name = name
        self._remaining = failures
        self._error = error
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        if self._remaining:
            self._remaining -= 1
            raise self._error("transient")
        return ModelResponse(text="ok", model=self._name)


def _ceiling(low: float, high: float) -> float:
    """Jitter stubbed to its upper bound, so the schedule is assertable."""
    return high


def _quiet(_seconds: float) -> None:
    return None


# --- classification ----------------------------------------------------------------


def test_transient_is_decided_by_status_code_and_by_name() -> None:
    assert is_transient(_OverloadedError())
    assert is_transient(APIConnectionError())
    assert not is_transient(_BadRequestError())
    assert not is_transient(ValueError("nothing to do with the provider"))


# --- retrying ----------------------------------------------------------------------


def test_a_transient_failure_is_retried_on_the_same_model() -> None:
    stub = _Stub("primary", failures=2)
    response = Resilient(stub, sleep=_quiet).complete(REQUEST)
    assert response.model == "primary"
    assert stub.calls == 3


def test_a_permanent_failure_is_not_retried() -> None:
    """Sending a 400 four times is four 400s."""
    stub = _Stub("primary", failures=1, error=_BadRequestError)
    with pytest.raises(_BadRequestError):
        Resilient(stub, sleep=_quiet).complete(REQUEST)
    assert stub.calls == 1


def test_backoff_doubles_and_is_capped() -> None:
    delays: list[float] = []
    stub = _Stub("primary", failures=99)
    resilient = Resilient(
        stub, attempts=4, base_delay=1.0, max_delay=3.0, sleep=delays.append, jitter=_ceiling
    )
    with pytest.raises(_OverloadedError):
        resilient.complete(REQUEST)
    assert delays == [1.0, 2.0, 3.0], "doubling, then held at the cap"
    assert stub.calls == 4, "one call per attempt, no sleep after the last"


def test_without_a_fallback_exhaustion_raises() -> None:
    stub = _Stub("primary", failures=99)
    with pytest.raises(_OverloadedError):
        Resilient(stub, attempts=2, sleep=_quiet).complete(REQUEST)


# --- substituting ------------------------------------------------------------------


def test_a_fallback_answers_only_after_the_primary_is_exhausted() -> None:
    primary, spare = _Stub("primary", failures=99), _Stub("spare")
    resilient = Resilient(primary, [spare], attempts=3, sleep=_quiet)
    assert resilient.complete(REQUEST).model == "spare"
    assert primary.calls == 3, "every attempt spent before substituting"
    assert spare.calls == 1


def test_a_substitution_is_recorded_rather_than_silent() -> None:
    """The whole reason the fallback list is empty by default."""
    resilient = Resilient(_Stub("primary", failures=99), [_Stub("spare")], attempts=1, sleep=_quiet)
    resilient.complete(REQUEST)
    assert len(resilient.substitutions) == 1
    substitution = resilient.substitutions[0]
    assert substitution.replaced == "primary"
    assert substitution.answered == "spare"
    assert "_OverloadedError" in substitution.after, "the failure that caused it is named"


def test_a_permanent_failure_never_reaches_the_fallback() -> None:
    """A 400 is not the provider being busy; another model answers it the same way."""
    primary, spare = _Stub("primary", failures=1, error=_BadRequestError), _Stub("spare")
    with pytest.raises(_BadRequestError):
        Resilient(primary, [spare], sleep=_quiet).complete(REQUEST)
    assert spare.calls == 0


def test_a_healthy_primary_records_no_substitution() -> None:
    resilient = Resilient(_Stub("primary"), [_Stub("spare")], sleep=_quiet)
    assert resilient.complete(REQUEST).model == "primary"
    assert resilient.substitutions == []


# --- the default -------------------------------------------------------------------


def test_the_shipped_configuration_substitutes_nothing() -> None:
    """Scored runs must not quietly change model. Setting this is a decision, not a default."""
    assert AgentSettings().fallback_models == []


def test_the_retry_loop_stops_when_the_run_s_budget_is_spent() -> None:
    """**Q33's other half.** Retries could outlive the budget they run inside.

    Four attempts against a 600 s per-call timeout is forty minutes of one logical call, and the
    harness's wall-clock check cannot interrupt a call already blocked. That is how
    `20260910T002657Z-ad-memory-squeeze` recorded 6596 s against a 600 s budget.

    The clock is injected, so this asserts the bound rather than waiting for it. Two attempts get
    made, not four: the deadline is checked before each attempt after the first, never mid-call -
    nothing here can interrupt a request in flight, and a bound that claimed to would not bind.
    """
    ticks = iter([0.0, 0.0, 700.0, 700.0])
    stub = _Stub("primary", failures=99)

    with pytest.raises(_OverloadedError):
        Resilient(
            stub,
            attempts=4,
            deadline_seconds=600.0,
            sleep=_quiet,
            clock=lambda: next(ticks),
        ).complete(REQUEST)

    assert stub.calls == 2, "the third attempt is past the deadline and is not made"


def test_no_deadline_leaves_the_retry_count_in_charge() -> None:
    """The default is unchanged behaviour. Every caller that does not pass a budget keeps the
    loop it had, so this cannot quietly shorten a retry somewhere nobody was looking."""
    stub = _Stub("primary", failures=99)

    with pytest.raises(_OverloadedError):
        Resilient(stub, attempts=3, sleep=_quiet).complete(REQUEST)

    assert stub.calls == 3


# --- T6.7 piece 5: the provider breaker ---------------------------------------------------------


def _resilient(primary: _Stub, fallbacks: list[_Stub] | None = None, **kw: Any) -> Resilient:
    return Resilient(
        primary,
        fallbacks or [],
        attempts=2,
        sleep=_quiet,
        jitter=_ceiling,
        breaker_cooldown_seconds=300.0,
        **kw,
    )


def test_one_exhausted_schedule_opens_the_model_and_the_next_call_is_refused_at_once() -> None:
    """**The tenth call of a run against a dead provider used to cost the same schedule as the
    first.** Now one exhaustion opens the model's breaker and every later call in the run is
    refused without a request, as `ProviderUnavailableError` - an outcome of its own, not a
    failure of the investigation."""
    from faultline.agents.model import ProviderUnavailableError

    primary = _Stub("m", failures=99)
    gateway = _resilient(primary)

    with pytest.raises(_OverloadedError):
        gateway.complete(REQUEST)
    assert primary.calls == 2, "the schedule, once"

    with pytest.raises(ProviderUnavailableError, match="provider unavailable: m open"):
        gateway.complete(REQUEST)
    assert primary.calls == 2, "open: nothing was sent"
    assert gateway.breakers["m"].trips == 1


def test_a_permanent_failure_does_not_count_against_the_provider() -> None:
    primary = _Stub("m", failures=1, error=_BadRequestError)
    gateway = _resilient(primary)

    with pytest.raises(_BadRequestError):
        gateway.complete(REQUEST)

    assert gateway.breakers["m"].trips == 0
    assert gateway.complete(REQUEST).text == "ok"


def test_an_open_primary_goes_straight_to_the_fallback_and_records_the_substitution() -> None:
    primary = _Stub("m", failures=99)
    spare = _Stub("spare")
    gateway = _resilient(primary, [spare])

    first = gateway.complete(REQUEST)
    second = gateway.complete(REQUEST)

    assert first.model == second.model == "spare"
    assert primary.calls == 2, "exhausted once, then refused at once - not exhausted again"
    assert spare.calls == 2
    assert [s.after for s in gateway.substitutions][1].startswith("m: circuit open")


def test_every_model_open_is_provider_unavailable_naming_all_of_them() -> None:
    from faultline.agents.model import ProviderUnavailableError

    primary = _Stub("m", failures=99)
    spare = _Stub("spare", failures=99)
    gateway = _resilient(primary, [spare])

    with pytest.raises(_OverloadedError):
        gateway.complete(REQUEST)
    with pytest.raises(ProviderUnavailableError) as refused:
        gateway.complete(REQUEST)

    assert refused.value.models == ["m", "spare"]
    assert primary.calls == spare.calls == 2


def test_after_the_cooldown_one_trial_call_half_opens_and_a_success_closes() -> None:
    clock = {"now": 0.0}
    primary = _Stub("m", failures=2)  # exhausts the first schedule, then answers
    gateway = _resilient(primary, clock=lambda: clock["now"])

    with pytest.raises(_OverloadedError):
        gateway.complete(REQUEST)
    clock["now"] += 300

    assert gateway.complete(REQUEST).text == "ok", "the trial"
    assert gateway.breakers["m"].state.value == "closed"
    assert gateway.complete(REQUEST).text == "ok"
