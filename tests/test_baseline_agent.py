"""B1 — one agent, all tools, no fan-out (T4.7).

The separation that makes B1 a control, the loop that makes it an agent, and the budget that
decides whether the comparison means anything.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from evalharness import baseline_agent as b1
from faultline.agents.budget import Budget
from faultline.agents.model import ModelRequest, ModelResponse
from faultline.tools.changelog import InMemoryChangeLog
from faultline.tools.settings import ToolSettings
from faultline.tools.tools import Tools

ANCHOR = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
NOW = datetime(2026, 9, 3, 12, 20, tzinfo=UTC)


class ScriptedModel:
    """Replies from a script, in order. Deterministic and inspectable."""

    def __init__(self, replies: list[str], name: str = "scripted-fake") -> None:
        self._replies = list(replies)
        self._name = name
        self.calls: list[ModelRequest] = []

    @property
    def name(self) -> str:
        return self._name

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        text = self._replies.pop(0) if self._replies else CONCLUDE
        return ModelResponse(text=text, model=self._name, input_tokens=100, output_tokens=50)


class RelentlessModel:
    """Always asks for another tool call - until it is asked for a verdict.

    **Deliberately not a script of N calls.** Scripting exactly the ceiling's worth would make
    the test assert the number it had just set. This model would call forever, so the budget is
    the only thing that can stop it, which is the property under test. It answers the verdict
    turn because exhaustion is meant to *finish* an investigation, not fail it (ADR-0020 §5).
    """

    name = "relentless-fake"

    def __init__(self) -> None:
        self.calls: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        asked_for_verdict = "Give your verdict now" in str(request.messages[-1]["content"])
        return ModelResponse(
            text=VERDICT if asked_for_verdict else call("logs", "frontend"),
            model=self.name,
            input_tokens=100,
            output_tokens=50,
        )


def call(tool: str, service: str, why: str = "checking") -> str:
    return json.dumps({"next": "call", "tool": tool, "service": service, "why": why})


CONCLUDE = json.dumps({"next": "conclude", "tool": None, "service": None, "why": "enough"})

VERDICT = json.dumps(
    {
        "root_cause": "adservice memory limit lowered until the process was killed",
        "fault_class": "resource_exhaustion",
        "remediation_class": "config_revert",
        "confidence": "medium",
        "evidence": ["tr_abc"],
        "reasoning": "the change is in the window and the errors follow it",
        "open_questions": ["whether the limit was lowered deliberately"],
    }
)


class Member:
    def __init__(self, service: str) -> None:
        self.service = service


class Triage:
    def __init__(self, alerting: list[str], radius: list[str] | None = None) -> None:
        self.alerting = [Member(s) for s in alerting]
        self.blast_radius = [Member(s) for s in (radius or alerting)]
        self.unmeasured_edges: list[str] = []


class Incident:
    id = "inc-1"
    title = "frontend error ratio above threshold"


def tools() -> Tools:
    return Tools(ToolSettings(), changes=InMemoryChangeLog())


def investigate(model: Any, budget: Budget | None = None, alerting: list[str] | None = None) -> Any:
    return b1.investigate(
        incident=Incident(),
        triage=Triage(alerting or ["frontend", "adservice"]),
        anchor=ANCHOR,
        now=NOW,
        tools=tools(),
        model=model,
        budget=budget or Budget(),
    )


# --- the separation that makes B1 a control ------------------------------------------------


def test_importing_b1_does_not_move_the_agents_stamp() -> None:
    """**The defect this module was designed around.**

    `prompt_digest()` hashes every `*_SYSTEM` string in `roles.py` plus `stamp._CONTRACTS`. A B1
    prompt placed in either would move the agent's `runtime_version` and orphan every figure
    recorded before it - a baseline that invalidates the thing it is a control for. The ledger
    constant lives in `test_harness_run.py`; this asserts against the same value.
    """
    from faultline.agents.stamp import prompt_digest

    # The ledger constant lives in `test_harness_run.py` as TOP3_DIGEST. Asserted by value here
    # rather than imported, so this file fails loudly if B1's prompt ever leaks into the
    # agent's digest - importing the constant would make the two move together and prove nothing.
    assert prompt_digest() == "42e34a1811c4", "B1 must not appear in the agent's stamp."


def test_b1s_prompt_is_not_a_role_prompt() -> None:
    """It is `B1_SYSTEM` in *this* module. The stamp scans `roles` for `*_SYSTEM` names, so a
    prompt living there would be stamped as one of the agent's whether or not it is one."""
    from faultline.agents import roles

    assert not hasattr(roles, "B1_SYSTEM")
    assert b1.B1_SYSTEM not in [
        getattr(roles, name) for name in dir(roles) if name.endswith("_SYSTEM")
    ]


def test_b1s_action_schema_is_not_one_of_the_agents_contracts() -> None:
    from faultline.agents.stamp import _CONTRACTS

    assert b1.B1Action not in _CONTRACTS


def test_b1_carries_its_own_runtime_distinct_from_the_agent_and_from_b0() -> None:
    from evalharness import baselines
    from faultline.agents.stamp import runtime_version as agent_runtime

    assert b1.runtime_version() not in {agent_runtime(), baselines.BASELINE_RUNTIME}
    assert ":B1:" in b1.runtime_version()


def test_the_b1_runtime_moves_when_its_prompt_moves(monkeypatch: pytest.MonkeyPatch) -> None:
    """**Derived, not hand-bumped, and this is the difference from B0.**

    B0's behaviour is code and carries a manual `BASELINE_VERSION`; a code change is visible in
    review. B1's behaviour is mostly a prompt, and a prompt edit is exactly what a manual marker
    forgets. Here nobody sets the marker, so nobody can forget it.
    """
    before = b1.runtime_version()
    monkeypatch.setattr(b1, "B1_SYSTEM", b1.B1_SYSTEM + "\n\nAlso, be brief.")

    assert b1.runtime_version() != before


def test_b1_carries_the_same_untrusted_content_rule_every_role_carries() -> None:
    """A baseline with a weaker injection defence would make a B1-versus-pipeline gap partly a
    difference in security posture, which is not what is being measured."""
    from faultline.agents.roles import UNTRUSTED_RULE

    assert UNTRUSTED_RULE in b1.system_prompt()


# --- the budget, which decides whether the comparison means anything -------------------------


def test_b1s_ceiling_is_the_sum_of_the_pipelines_per_specialist_bounds() -> None:
    """Equal permission, measured consumption. One specialist's bound would starve B1; no bound
    would make it a different experiment."""
    budget = Budget(max_tool_calls_per_specialist=12)

    assert b1.tool_budget(budget) == 48


def test_a_per_specialist_override_raises_b1s_ceiling_too() -> None:
    """T4.7 measured the `changes` override because the pipeline needed it. B1 asks the same
    questions of the same world, so it inherits the same measurement rather than a stale default."""
    budget = Budget(max_tool_calls_per_specialist=12, per_specialist_tool_calls={"changes": 20})

    assert b1.tool_budget(budget) == 12 * 3 + 20


# --- the loop ------------------------------------------------------------------------------


def test_it_calls_what_it_asked_for_and_then_concludes() -> None:
    model = ScriptedModel([call("changes", "adservice"), CONCLUDE, VERDICT])

    run = investigate(model)

    assert run.error is None
    assert [(look.tool, look.service) for look in run.looks] == [("changes", "adservice")]
    assert run.verdict.fault_class == "resource_exhaustion"
    assert run.verdict.remediation_class == "config_revert"


def test_every_envelope_reaches_the_next_turn() -> None:
    """**The property that distinguishes B1 from the fan-out, in one assertion.**

    The pipeline's specialists each read one envelope and never see each other's. B1's second
    choice is made by a model that has read the first result. If that were not true, B1 would be
    a slower fan-out rather than a single agent, and the comparison would measure nothing.
    """
    model = ScriptedModel([call("changes", "adservice"), call("logs", "adservice"), VERDICT])

    run = investigate(model)

    second_choice = model.calls[1]
    transcript = "\n".join(str(message["content"]) for message in second_choice.messages)
    assert run.looks[0].result_id in transcript, "the first result must be in view for the second"
    assert "<tool_result " in transcript


def test_a_tool_call_goes_through_the_pipelines_own_query_path() -> None:
    """B1 dispatches via `Specialist.query`, so `metrics` means `metric_baseline` on the error
    ratio for B1 exactly as it does for the pipeline. A parallel implementation would drift, and
    a B1-versus-pipeline difference would then be partly a difference in what was *asked*."""
    model = ScriptedModel([call("metrics", "frontend"), CONCLUDE, VERDICT])

    run = investigate(model)

    assert run.looks[0].envelope.startswith("<tool_result ")
    assert 'tool="metric_baseline"' in run.looks[0].envelope


def test_an_incomplete_call_is_re_asked_rather_than_guessed() -> None:
    """A `call` naming no service is not a call. Guessing one would invent a dispatch the model
    did not make and attribute it to the model."""
    incomplete = json.dumps({"next": "call", "tool": "logs", "service": None, "why": ""})
    model = ScriptedModel([incomplete, call("logs", "frontend"), CONCLUDE, VERDICT])

    run = investigate(model)

    assert [look.service for look in run.looks] == ["frontend"]


def test_concluding_without_looking_at_anything_is_an_error_not_a_verdict() -> None:
    """A verdict reached without a single tool call is not an investigation, and scoring it would
    credit the model's prior to the baseline's method. That is B2's measurement, not B1's."""
    run = investigate(ScriptedModel([CONCLUDE, VERDICT]))

    assert run.verdict is None
    assert run.error is not None
    assert "without making a single tool call" in run.error


def test_exhausting_the_budget_finishes_the_investigation_rather_than_failing_it() -> None:
    """ADR-0020 §5. The model is told its budget is spent and gets its verdict turn on what it
    already has - and the run is flagged, because T4.2 reports exhausted runs separately rather
    than pooling them."""
    budget = Budget(max_tool_calls_per_specialist=1)  # ceiling of 4
    model = RelentlessModel()

    run = investigate(model, budget=budget)

    assert run.budget_exhausted is True
    assert run.tool_calls == 4, "stopped at the ceiling, not past it"
    assert run.verdict is not None, "exhaustion finishes the investigation"


def test_usage_is_summed_across_every_turn() -> None:
    """B1's cost is the whole conversation, not its last call. A per-call figure would make the
    single agent look cheaper than it is, which is the direction that flatters the baseline."""
    model = ScriptedModel([call("logs", "frontend"), CONCLUDE, VERDICT])

    run = investigate(model)

    assert run.turns == 3
    assert run.tokens_in == 300
    assert run.tokens_out == 150


def test_a_reply_that_never_validates_is_recorded_rather_than_raised() -> None:
    """A baseline that crashes the harness cannot be scored, and a discard is a worse outcome
    than a recorded failure - the failure is data about the baseline."""
    model = ScriptedModel(["not json", "still not json"])

    run = investigate(model)

    assert run.verdict is None
    assert run.error is not None and "could not choose" in run.error


# --- scored by the same code path as everything else ----------------------------------------


def test_the_artifact_has_every_field_the_scorer_reads() -> None:
    model = ScriptedModel([call("changes", "adservice"), CONCLUDE, VERDICT])
    run = investigate(model)

    written = b1.artifact(
        incident_id="i-1",
        trajectory_id="t-1",
        blast_radius=["frontend", "adservice"],
        unmeasured_edges=1,
        exclude_origin="scenario:ad-memory-squeeze",
        run=run,
    )

    for field_name in (
        "trajectory_id",
        "blast_radius",
        "unmeasured_edges",
        "verdict",
        "flags",
        "failed_dispatches",
        "narrative_error",
    ):
        assert field_name in written, f"the scorer reads {field_name}"
    assert written["verdict"]["fault_class"] == "resource_exhaustion"
    assert written["verdict"]["remediation_class"] == "config_revert"


def test_the_artifact_leaves_the_pipelines_fields_empty_rather_than_absent() -> None:
    """A reader diffing a B1 artifact against the pipeline's should see which parts B1 does not
    have, rather than which keys someone forgot. B1 has no retrieval, no proposer, no scribe."""
    run = investigate(ScriptedModel([call("logs", "frontend"), CONCLUDE, VERDICT]))
    written = b1.artifact("i", "t", [], 0, None, run)

    assert written["retrieved"] == []
    assert written["proposal"] is None
    assert written["disclosure"] == {}


def test_an_exhausted_run_is_flagged_in_the_artifact() -> None:
    budget = Budget(max_tool_calls_per_specialist=1)
    run = investigate(RelentlessModel(), budget=budget)

    assert "budget_exhausted" in b1.artifact("i", "t", [], 0, None, run)["flags"]


def test_both_clis_offer_b1_and_neither_reaches_a_backend_to_say_so() -> None:
    """`--help` must not need Postgres or a model - the discipline every command in this
    repository keeps. A baseline wired at import time would break it for all four."""
    from evalharness.run import parser as eval_parser
    from faultline.agents.cli import parser as investigate_parser

    for build in (eval_parser, investigate_parser):
        flag = next(a for a in build()._actions if a.dest == "baseline")
        assert set(flag.choices or ()) == {"b0", "b1", "b2"}


def test_a_b1_run_cannot_share_a_config_fingerprint_with_an_agent_or_b0_run() -> None:
    """T4.7 wants baselines as *"ordinary configs in the eval DB"*, which only means anything if
    they are **distinct** configs."""
    from evalharness import evaldb

    common = {"scenario_id": "ad-memory-squeeze", "models": {"planner": "claude-opus-5"}}
    agent = evaldb.fingerprint(common)
    b0 = evaldb.fingerprint({**common, "baseline": "b0"})
    b1_config = evaldb.fingerprint({**common, "baseline": "b1"})

    assert len({agent.fingerprint, b0.fingerprint, b1_config.fingerprint}) == 3
