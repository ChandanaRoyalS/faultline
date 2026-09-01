"""Retrying, substituting, and the difference between them (T2.5, ADR-0031).

A retry changes nothing anything records: the same model answered. A substitution changes
which model answered, and `freeze.model_map()` records the model a run was *configured* with
— so a silent fallback would leave the freeze asserting a model that never ran. These tests
pin both halves: that transient failures are retried, and that a substitution is never quiet.
"""

from __future__ import annotations

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
