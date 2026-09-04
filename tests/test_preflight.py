"""The pre-flight model check (Q20).

Dev sweep 8 injected `product-catalog-flag-failure` **four times** and discarded all four when the
API answered `credit balance too low` at the triage call. Two more scenarios never started for the
same reason: sixteen non-scored outcomes against six scored, and the cause was not the pipeline.

The harness already refuses before touching the world when the *world* is not quiet. The model's
reachability was not checked at all, so a run would break the world first and discover it could
not investigate second.
"""

from __future__ import annotations

from typing import Any

import pytest

from evalharness import preflight
from faultline.agents.model import ModelRequest, ModelResponse


class Reachable:
    name = "reachable-model"

    def __init__(self) -> None:
        self.calls: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        return ModelResponse(text="ok", model=self.name, input_tokens=4, output_tokens=1)


class Broke:
    """The exact failure that cost sweep 8 three scenarios: a valid key with no balance."""

    name = "broke-model"

    def complete(self, request: ModelRequest) -> ModelResponse:
        raise RuntimeError(
            "HTTP 400 invalid_request_error: Your credit balance is too low to access the "
            "Anthropic API."
        )


class UnheardOfError(Exception):
    """Something `preflight` has never seen and cannot have anticipated."""


class Exotic:
    name = "exotic-model"

    def complete(self, request: ModelRequest) -> ModelResponse:
        raise UnheardOfError("the transport did something new")


class Interrupted:
    """Ctrl-C during the probe. `KeyboardInterrupt` is a `BaseException`, so `except Exception`
    does not catch it - which is correct and is asserted below."""

    name = "interrupted"

    def complete(self, request: ModelRequest) -> ModelResponse:
        raise KeyboardInterrupt


# --- one token on the configured model --------------------------------------------------------


def test_the_probe_is_capped_at_one_token_and_its_answer_is_discarded() -> None:
    """What is being tested is whether the call is *possible*, not what the model says. A probe
    that asked something real would tempt a future reader to use the answer."""
    model = Reachable()

    result = preflight.probe(model, "reachable-model")

    assert result.ok is True
    assert model.calls[0].max_tokens == preflight.PROBE_TOKENS == 1
    assert "token(s) billed" in result.detail


def test_a_credit_balance_failure_is_caught() -> None:
    """**The failure that would have saved sweep 8 three scenarios.** A models-list call would
    have passed this: the key was valid, the balance was not."""
    result = preflight.probe(Broke(), "broke-model")

    assert result.ok is False
    assert "credit balance" in result.detail


def test_an_unexpected_exception_becomes_a_failed_check_rather_than_a_crash() -> None:
    """A pre-flight check that itself raises would abort the run in a path with no manifest and no
    recorded reason - strictly worse than the problem it exists to prevent."""
    result = preflight.probe(Exotic(), "exotic-model")

    assert result.ok is False
    assert result.checked is True
    assert "something new" in result.detail


def test_a_keyboard_interrupt_is_not_swallowed_as_an_unreachable_model() -> None:
    """**`except Exception`, deliberately not `except BaseException`.**

    Ctrl-C during the probe is the operator stopping the sweep, and reporting it as "the model
    could not be reached" would be the harness lying about why it stopped. Found by writing this
    file: the first fixture for the unexpected-exception case raised `KeyboardInterrupt` and the
    test hung the runner, which is the behaviour working.
    """
    with pytest.raises(KeyboardInterrupt):
        preflight.probe(Interrupted(), "interrupted")


# --- refusing, and what a refusal is not ------------------------------------------------------


def test_an_unreachable_model_refuses_before_anything_is_injected() -> None:
    with pytest.raises(preflight.PreflightError) as caught:
        preflight.require(None, "broke-model", Broke)

    message = str(caught.value)
    assert "Nothing was injected" in message
    assert "not a discard" in message
    assert "four times" in message, "the message names the evidence that motivated the check"


def test_a_reachable_model_returns_a_row_for_the_manifest() -> None:
    result = preflight.require(None, "reachable-model", Reachable)

    assert result.ok is True
    assert result.as_dict()["model"] == "reachable-model"
    assert result.as_dict()["checked"] is True


def test_b0_skips_the_check_without_constructing_a_client() -> None:
    """**B0's whole claim is that it makes no model call and costs \\$0.00.** Building a client
    just to skip the check would put a connection in the latency of a baseline that has none - and
    refusing B0 for an unreachable model would refuse a run that cannot be affected by one."""
    built: list[Any] = []

    def build() -> Any:
        built.append(object())
        return Reachable()

    result = preflight.require("b0", "any-model", build)

    assert built == [], "no client was constructed"
    assert result.checked is False
    assert "no model call" in result.skipped_because


@pytest.mark.parametrize("baseline", [None, "b1", "b2"])
def test_every_arm_that_calls_a_model_is_checked(baseline: str | None) -> None:
    """B1 and B2 both make model calls, so both can be stopped by an unreachable model - and both
    would otherwise inject first and find out second, exactly as sweep 8 did."""
    with pytest.raises(preflight.PreflightError):
        preflight.require(baseline, "broke-model", Broke)


# --- it is wired where it costs least ---------------------------------------------------------


def test_the_check_runs_before_the_baseline_gate_in_the_harness() -> None:
    """**Cheapest check first.** The gate can wait out a 300-second settle window, and discovering
    an unreachable model after that wait would throw the wait away as well as the run. Asserted
    against the source order rather than by running the harness, which needs a world."""
    from pathlib import Path

    source = Path("src/evalharness/run.py").read_text()

    assert source.index("preflight.require(") < source.index('print("baseline gate...")')


def test_a_preflight_refusal_exits_three_and_is_not_recorded_as_a_discard() -> None:
    """ADR-0022 §3.3 keeps the discard number honest precisely so it means something, and a run
    that never started is not a run that failed.

    **Read as an AST, not as a 700-character slice of source.** This test took the first 700
    characters after `except preflight.PreflightError` and looked for `return 3` in them, and it
    broke the moment a comment was added to that handler explaining why a refusal is not a
    discard - the check failed on the prose written to document the very rule it enforces. Ninth
    instance of substring-on-prose in this repository, and the technique ADR-0032 settled after
    the third: walk the tree and ask the structural question.
    """
    import ast
    import inspect

    from evalharness import run as run_module

    tree = ast.parse(inspect.getsource(run_module.main))
    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler)
        and node.type is not None
        and ast.unparse(node.type).endswith("PreflightError")
    )
    returns = {
        node.value.value
        for node in ast.walk(handler)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant)
    }
    calls = {
        ast.unparse(node.func).rsplit(".", 1)[-1]
        for node in ast.walk(handler)
        if isinstance(node, ast.Call)
    }

    assert returns == {3}
    assert "discard" not in calls, "a refusal before injection is not a discard"
    assert "refuse" in calls, "and it must say so on disk, like the gate's refusal does"
