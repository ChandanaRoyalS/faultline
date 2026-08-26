"""T3.3: the planner and the four specialists. Fake model only - conftest sees to that.

Every model reply here is scripted, so what is under test is the loop, the schemas and the
budget rather than the model's judgement.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from faultline.agents.budget import Budget, BudgetState
from faultline.agents.contracts import DispatchPlan, SpecialistFindings
from faultline.agents.investigation import Investigation
from faultline.agents.model import LanguageModel, ModelRequest, ModelResponse
from faultline.agents.roles import Planner, build_specialists
from faultline.agents.trajectory import InMemoryTrajectoryStore, StepKind
from faultline.agents.triage import Triage
from faultline.context.catalog import ServiceCatalog
from faultline.context.settings import ContextSettings
from faultline.orchestrator.models import Episode, Incident, Severity
from faultline.tools.changelog import InMemoryChangeLog
from faultline.tools.settings import ToolSettings
from faultline.tools.tools import Tools

ANCHOR = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)

FINDINGS_REPLY = json.dumps(
    {
        "found": [{"statement": "no errors in window", "result_id": "X", "confidence": "high"}],
        "ruled_out": [
            {"hypothesis": "the service was erroring", "result_id": "X", "why": "ratio flat at 0"}
        ],
        "note": "",
    }
)


class ScriptedModel:
    """Replies by role, from a script. Deterministic and inspectable."""

    def __init__(self, replies: dict[str, list[str]], name: str = "scripted-fake") -> None:
        self._replies = {role: list(texts) for role, texts in replies.items()}
        self._name = name
        self.calls: list[ModelRequest] = []

    @property
    def name(self) -> str:
        return self._name

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        queue = self._replies.get(request.role)
        text = queue.pop(0) if queue else FINDINGS_REPLY
        return ModelResponse(text=text, model=self._name, input_tokens=100, output_tokens=50)


def plan_reply(dispatches: list[dict[str, str]], skipped: list[dict[str, str]]) -> str:
    return json.dumps({"dispatches": dispatches, "skipped": skipped, "rationale": "because"})


def incident_of(service: str) -> Incident:
    incident = Incident(opened_at=ANCHOR, last_activity_at=ANCHOR)
    incident.episodes["e0"] = Episode(
        episode_key="e0",
        fingerprint="f0",
        service=service,
        severity=Severity.CRITICAL,
        alertname="ServiceHighErrorRate",
        starts_at=ANCHOR,
        attached_at=ANCHOR,
    )
    return incident


def triage_of(service: str) -> Any:
    catalog = ServiceCatalog.from_snapshot()
    return Triage(catalog, ContextSettings().hop_radius).run(incident_of(service))


def investigation(model: LanguageModel, budget: Budget) -> tuple[Investigation, Any]:
    tools = Tools(ToolSettings(), changes=InMemoryChangeLog())
    store = InMemoryTrajectoryStore()
    return (
        Investigation(
            planner=Planner(model),
            specialists=build_specialists(tools, model),
            store=store,
            model=model,
            budget=budget,
        ),
        store,
    )


# --- the planner chooses ------------------------------------------------------


def test_a_plan_may_dispatch_fewer_than_four_specialists() -> None:
    """**The load table is why the planner exists.** Change and metrics were consulted in 10 of
    10 rehearsed investigations, logs in 7, traces in 2 - a planner that always dispatches four
    is a fan-out with a prompt in front of it."""
    model = ScriptedModel(
        {
            "planner": [
                plan_reply(
                    [
                        {
                            "specialist": "changes",
                            "service": "cartservice",
                            "question": "what changed",
                            "reason": "10 of 10",
                        }
                    ],
                    [
                        {"specialist": "metrics", "reason": "triage already has the ratios"},
                        {"specialist": "logs", "reason": "no log signal expected"},
                        {"specialist": "traces", "reason": "not a latency incident"},
                    ],
                )
            ]
        }
    )
    engine, _ = investigation(model, Budget(max_dispatch_rounds=1))

    result = engine.run("incident-1", triage_of("cartservice"), ANCHOR)

    assert len(result.plans[0].dispatches) == 1
    assert {s.specialist for s in result.plans[0].skipped} == {"metrics", "logs", "traces"}
    assert [run.specialist for run in result.runs] == ["changes"]


def test_a_plan_must_say_what_it_decided_against() -> None:
    """`skipped` is a required field, so a four-dispatch plan with an empty `skipped` is
    expressible and a plan that silently omitted a specialist is not."""
    assert "skipped" in DispatchPlan.model_fields
    assert DispatchPlan.model_fields["skipped"].is_required()

    with pytest.raises(ValidationError):
        DispatchPlan.model_validate({"dispatches": [], "skipped": [], "rationale": "x"})


# --- specialist output --------------------------------------------------------


def test_ruled_out_is_in_the_schema_rather_than_being_optional_prose() -> None:
    """`ARTIFACTS.md`: the dead ends are "the most useful thing in the document". A default of
    `[]` would let a specialist discard half its work silently."""
    assert SpecialistFindings.model_fields["ruled_out"].is_required()
    assert SpecialistFindings.model_fields["found"].is_required()

    with pytest.raises(ValidationError):
        SpecialistFindings.model_validate({"found": []})


def test_findings_cite_evidence_by_result_id_and_the_envelope_is_stored_verbatim() -> None:
    """ADR-0020 §4's leak boundary at the point it is first crossed: the raw text stays in the
    store and only references travel onward."""
    model = ScriptedModel(
        {
            "planner": [
                plan_reply(
                    [
                        {
                            "specialist": "changes",
                            "service": "cartservice",
                            "question": "what changed",
                            "reason": "start here",
                        }
                    ],
                    [{"specialist": "traces", "reason": "no"}],
                )
            ]
        }
    )
    engine, store = investigation(model, Budget(max_dispatch_rounds=1))

    result = engine.run("incident-2", triage_of("cartservice"), ANCHOR)

    run = result.runs[0]
    assert run.findings.found[0].result_id
    trajectory = next(iter(store.trajectories.values()))
    call = trajectory.tool_calls[0]
    assert call.envelope == run.envelope
    assert call.envelope.startswith("<tool_result ")
    assert 'trust="untrusted"' in call.envelope


def test_every_dispatch_lands_in_the_trajectory_with_the_effective_model_map() -> None:
    model = ScriptedModel(
        {
            "planner": [
                plan_reply(
                    [
                        {
                            "specialist": "changes",
                            "service": "cartservice",
                            "question": "q",
                            "reason": "r",
                        }
                    ],
                    [{"specialist": "logs", "reason": "no"}],
                )
            ]
        }
    )
    tools = Tools(ToolSettings(), changes=InMemoryChangeLog())
    store = InMemoryTrajectoryStore()
    engine = Investigation(
        planner=Planner(model),
        specialists=build_specialists(tools, model),
        store=store,
        model=model,
        budget=Budget(max_dispatch_rounds=1),
        role_models={"scribe": "claude-haiku-4-5"},
    )

    engine.run("incident-3", triage_of("cartservice"), ANCHOR)

    trajectory = next(iter(store.trajectories.values()))
    assert trajectory.role_models == {"scribe": "claude-haiku-4-5"}
    kinds = [step.kind for step in trajectory.steps]
    assert kinds == [StepKind.COMPLETION, StepKind.TOOL_CALL, StepKind.COMPLETION]
    assert all(step.tokens_in or step.tool_call for step in trajectory.steps)


# --- the budget ---------------------------------------------------------------


def test_budget_exhaustion_flags_the_result_rather_than_raising() -> None:
    """ADR-0020 §5: a partial diagnosis is scoreable and a `FAILED` incident is not. An
    exception would unwind past the point where the partial answer exists."""
    model = ScriptedModel(
        {
            "planner": [
                plan_reply(
                    [
                        {
                            "specialist": "changes",
                            "service": "cartservice",
                            "question": "q",
                            "reason": "r",
                        },
                        {
                            "specialist": "metrics",
                            "service": "cartservice",
                            "question": "q",
                            "reason": "r",
                        },
                    ],
                    [{"specialist": "logs", "reason": "no"}],
                )
            ]
        }
    )
    engine, store = investigation(model, Budget(max_tokens=200, max_dispatch_rounds=1))

    result = engine.run("incident-4", triage_of("cartservice"), ANCHOR)

    assert result.budget_exhausted
    assert result.exhausted_reason and "tokens" in result.exhausted_reason
    assert next(iter(store.trajectories.values())).budget_exhausted is True
    assert next(iter(store.trajectories.values())).outcome == "budget_exhausted"


def test_the_one_follow_up_round_cap_is_structural() -> None:
    """Enforced by the rounds bound, not by prose: a planner that keeps asking cannot keep
    being asked."""
    plan = plan_reply(
        [{"specialist": "changes", "service": "cartservice", "question": "q", "reason": "r"}],
        [{"specialist": "logs", "reason": "no"}],
    )
    model = ScriptedModel({"planner": [plan, plan, plan, plan]})
    engine, _ = investigation(model, Budget())

    result = engine.run("incident-5", triage_of("cartservice"), ANCHOR)

    assert len(result.plans) == 2, "the plan and at most one follow-up"
    assert Budget().max_dispatch_rounds == 2


def test_the_rounds_bound_is_checked_before_a_third_round_is_planned() -> None:
    """The bound is on the budget object, so it cannot be talked past by a prompt."""
    state = BudgetState(Budget(max_dispatch_rounds=2))

    assert state.start_round() and state.start_round()
    assert not state.start_round()
    assert state.exhausted_reason and "dispatch rounds" in state.exhausted_reason


def test_a_specialist_tool_call_cap_stops_that_specialist_not_the_investigation() -> None:
    state = BudgetState(Budget(max_tool_calls_per_specialist=1))
    state.record_tool_call("metrics")

    assert not state.may_call_tool("metrics")
    assert state.exhausted_reason and "metrics tool calls" in state.exhausted_reason


def test_a_specialist_whose_output_never_validates_fails_alone() -> None:
    """Found on the first live dispatch: a reply cut off at `max_tokens` is truncated JSON, and
    it arrives looking like malformed JSON. Twice in a row it raised out of the loop and killed
    an investigation that already had findings from three other specialists.

    A specialist that cannot produce valid output is one specialist's failure. It is recorded as
    a step so scoring sees it rather than finding it merely absent, and the rest continue - the
    same argument ADR-0020 §5 makes about budget exhaustion, applied to a failure it did not
    anticipate.
    """
    model = ScriptedModel(
        {
            "planner": [
                plan_reply(
                    [
                        {
                            "specialist": "changes",
                            "service": "cartservice",
                            "question": "q",
                            "reason": "r",
                        },
                        {
                            "specialist": "metrics",
                            "service": "cartservice",
                            "question": "q",
                            "reason": "r",
                        },
                    ],
                    [{"specialist": "traces", "reason": "no"}],
                )
            ],
            "changes": ['{"found": [{"statement": "cut off her', '{"still": "broken'],
        }
    )
    engine, store = investigation(model, Budget(max_dispatch_rounds=1))

    result = engine.run("incident-6", triage_of("cartservice"), ANCHOR)

    assert [name for name, _ in result.failed_dispatches] == ["changes"]
    assert [run.specialist for run in result.runs] == ["metrics"], "the others still ran"
    trajectory = next(iter(store.trajectories.values()))
    failures = [s for s in trajectory.steps if "schema_failure" in s.payload]
    assert len(failures) == 1, "the failure is a step, not an absence"


def test_a_truncated_reply_is_re_asked_as_truncation_rather_than_as_malformed_json() -> None:
    """The re-ask that merely said "that did not validate" invited the same too-long reply
    again. Naming the failure is what makes the one retry worth having."""
    replies = ['{"found": [{"statement": "cut off her', FINDINGS_REPLY]

    class Truncating(ScriptedModel):
        def complete(self, request: ModelRequest) -> ModelResponse:
            response = super().complete(request)
            stop = (
                "max_tokens"
                if response.text.startswith('{"found": [{"statement": "cut')
                else "end_turn"
            )
            return ModelResponse(
                text=response.text,
                model=response.model,
                input_tokens=100,
                output_tokens=50,
                stop_reason=stop,
            )

    model = Truncating({"metrics": replies})
    from faultline.agents.roles import ask

    completion = ask(
        model,
        ModelRequest(system="s", messages=[{"role": "user", "content": "u"}], role="metrics"),
        SpecialistFindings,
    )

    assert completion.attempts == 2
    nudge = model.calls[-1].messages[-1]["content"]
    assert "cut off at the token limit" in nudge and "shorter" in nudge
