"""T3.3: the planner and the four specialists. Fake model only - conftest sees to that.

Every model reply here is scripted, so what is under test is the loop, the schemas and the
budget rather than the model's judgement.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from faultline.agents.budget import Budget, BudgetState
from faultline.agents.contracts import DispatchPlan, SpecialistFindings
from faultline.agents.investigation import Investigation
from faultline.agents.model import LanguageModel, ModelRequest, ModelResponse
from faultline.agents.roles import (
    Planner,
    SchemaValidationError,
    Scribe,
    Synthesizer,
    build_specialists,
)
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


# --- synthesizer and scribe ---------------------------------------------------


VERDICT_REPLY = json.dumps(
    {
        "root_cause": "the cart service could not reach its datastore",
        "fault_class": "bad_config",
        "remediation_class": "config_revert",
        "confidence": "high",
        "evidence": ["RID"],
        "reasoning": "the change record and the crash loop agree",
        "open_questions": ["whether the port was ever correct"],
    }
)


def draft_reply(citations: list[str]) -> str:
    return json.dumps(
        {
            "title": "Cart lookups failing at checkout",
            "sections": [
                {
                    "heading": "What was observed",
                    "body": "Checkout began failing at T+0. The storefront still rendered.",
                    "citations": citations,
                }
            ],
        }
    )


def full_engine(model: LanguageModel, budget: Budget, corpus: Any = None) -> tuple[Any, Any]:

    tools = Tools(ToolSettings(), changes=InMemoryChangeLog())
    store = InMemoryTrajectoryStore()
    engine = Investigation(
        planner=Planner(model),
        specialists=build_specialists(tools, model),
        store=store,
        model=model,
        budget=budget,
        synthesizer=Synthesizer(model),
        scribe=Scribe(model),
        corpus=corpus,
    )
    return engine, store


class FakeCorpus:
    """Records what it was asked, so the exclusion can be asserted on the call, not the result."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str | None]] = []

    def search(self, query: str, k: int = 5, exclude_origin: str | None = None) -> list[Any]:
        self.calls.append((query, k, exclude_origin))
        return []


ONE_DISPATCH = plan_reply(
    [{"specialist": "changes", "service": "cartservice", "question": "q", "reason": "r"}],
    [{"specialist": "logs", "reason": "later"}],
)


def test_every_retrieval_row_carries_exclude_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    """**ADR-0008's axis 2, at the point it is first consumed live.** The harness sets the
    scenario under test and the row records it, which is where T4.1b reads the assertion."""
    monkeypatch.setenv("FAULTLINE_EVAL_SCENARIO", "cart-redis-misconfig")
    corpus = FakeCorpus()
    model = ScriptedModel(
        {"planner": [ONE_DISPATCH], "synthesizer": [VERDICT_REPLY], "scribe": [draft_reply([])]}
    )
    engine, store = full_engine(model, Budget(max_dispatch_rounds=1), corpus)

    result = engine.run("incident-7", triage_of("cartservice"), ANCHOR)

    assert result.exclude_origin == "scenario:cart-redis-misconfig"
    assert corpus.calls and corpus.calls[0][2] == "scenario:cart-redis-misconfig"
    rows = [s.retrieval for s in store.trajectories[result.trajectory.id].steps if s.retrieval]
    assert len(rows) == 1
    assert rows[0].exclude_origin == "scenario:cart-redis-misconfig"


def test_production_retrieval_carries_no_exclusion_and_that_is_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A live incident has no origin to exclude. `None` has to be distinguishable from a scored
    run that forgot one."""
    monkeypatch.delenv("FAULTLINE_EVAL_SCENARIO", raising=False)
    corpus = FakeCorpus()
    model = ScriptedModel(
        {"planner": [ONE_DISPATCH], "synthesizer": [VERDICT_REPLY], "scribe": [draft_reply([])]}
    )
    engine, _ = full_engine(model, Budget(max_dispatch_rounds=1), corpus)

    result = engine.run("incident-8", triage_of("cartservice"), ANCHOR)

    assert result.exclude_origin is None
    assert corpus.calls[0][2] is None


def test_a_flagged_investigation_produces_a_flagged_verdict_not_silence() -> None:
    """ADR-0020 §5. The synthesizer is told what is incomplete and must account for it; the
    flags travel on the trajectory so T4.2 can report those runs separately."""
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
            ],
            "synthesizer": [VERDICT_REPLY],
            "scribe": [draft_reply([])],
        }
    )
    engine, store = full_engine(model, Budget(max_tokens=200, max_dispatch_rounds=1))

    result = engine.run("incident-9", triage_of("cartservice"), ANCHOR)

    assert result.budget_exhausted
    assert result.verdict is not None, "a flagged investigation still produces a verdict"
    assert result.flags and "budget exhausted" in result.flags[0]
    verdict_steps = [
        s for s in store.trajectories[result.trajectory.id].steps if s.payload.get("flags")
    ]
    assert verdict_steps and verdict_steps[0].payload["flags"] == result.flags


def test_the_scribe_cannot_quote_a_result_id_the_store_does_not_hold() -> None:
    """**This is where thesis 1 is cut.** A citation nobody can resolve is what a fabricated one
    looks like, so it is refused rather than dropped - dropping it would turn an invented
    reference into unsupported prose."""
    from faultline.agents.contracts import NarrativeDraft
    from faultline.agents.narrative import UnknownCitationError, render

    draft = NarrativeDraft.model_validate(json.loads(draft_reply(["tr_never_stored"])))

    with pytest.raises(UnknownCitationError, match="not in the trajectory store"):
        render(draft, InMemoryTrajectoryStore())


def test_a_quote_comes_from_the_stored_envelope_not_from_the_drafts_text() -> None:
    """The scribe emits references; the renderer resolves them. Free-form pass-through from tool
    output to corpus material has nowhere to happen."""
    from faultline.agents.contracts import NarrativeDraft
    from faultline.agents.narrative import render
    from faultline.agents.trajectory import StepKind, ToolCallRecord, Trajectory, TrajectoryStep

    store = InMemoryTrajectoryStore()
    trajectory = Trajectory(incident_id="i", model="m", effort="high", started_at=ANCHOR)
    trajectory.add(
        TrajectoryStep(
            seq=1,
            role="logs",
            kind=StepKind.TOOL_CALL,
            at=ANCHOR,
            tool_call=ToolCallRecord(
                tool="logql_query",
                request={},
                result_id="tr_stored",
                envelope=(
                    '<tool_result id="tr_stored" trust="untrusted">\n'
                    "line one\nline two\n</tool_result:tr_stored>"
                ),
            ),
        )
    )
    store.save(trajectory)
    draft = NarrativeDraft.model_validate(json.loads(draft_reply(["tr_stored"])))

    rendered = render(draft, store)

    assert "line one" in rendered, "the quote came from the store"
    assert "Evidence `tr_stored`" in rendered


def test_the_leak_guard_runs_over_the_finished_narrative() -> None:
    """The T2.6 banned vocabulary, over the rendered text. A record naming a class of failure
    hands the reader the answer in one word."""
    from faultline.agents.contracts import NarrativeDraft
    from faultline.agents.narrative import NarrativeLeakError, leaked_words, render

    leaking = NarrativeDraft.model_validate(
        {
            "title": "A bad_config incident",
            "sections": [
                {"heading": "What happened", "body": "the injected fault", "citations": []}
            ],
        }
    )

    with pytest.raises(NarrativeLeakError) as raised:
        render(leaking, InMemoryTrajectoryStore())

    assert "bad_config" in str(raised.value)
    assert leaked_words("a clean record about a failure") == []
    assert "faultline" in leaked_words("written by faultline")


class CitingScribeModel(ScriptedModel):
    """A scribe that cites whatever result_id this run actually produced.

    The real scribe does exactly this - it reads the ids out of the findings it is given - and
    a fixed citation string cannot stand in for it, because result ids are minted per call.
    """

    def __init__(self, replies: dict[str, list[str]]) -> None:
        super().__init__(replies)
        self.seen: list[str] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.seen.extend(re.findall(r"tr_[0-9a-f]+", str(request)))
        if request.role == "scribe":
            assert self.seen, "no envelope reached the model, so there is nothing to cite"
            self.calls.append(request)
            return ModelResponse(text=draft_reply([self.seen[-1]]), model=self.name)
        return super().complete(request)


def test_the_trajectory_is_persisted_before_the_scribe_resolves_citations() -> None:
    """Found on the first end-to-end run: the scribe cited real result_ids and every one was
    refused, because the trajectory was still only in memory when the renderer looked.

    The guard fired correctly on evidence that genuinely existed - which is the worst kind of
    correct, since it looks exactly like the fabricated-citation case it is there to catch.
    """
    model = CitingScribeModel(
        {"planner": [ONE_DISPATCH], "synthesizer": [VERDICT_REPLY], "scribe": []}
    )
    engine, store = full_engine(model, Budget(max_dispatch_rounds=1))
    result = engine.run("incident-10", triage_of("cartservice"), ANCHOR)

    cited = result.draft.sections[0].citations[0]
    assert store.envelope(cited) is not None, "saved before the scribe's citation is resolved"
    assert result.narrative_error is None, result.narrative_error
    assert result.narrative is not None
    assert cited in result.narrative


def test_three_dispatches_of_one_specialist_all_reach_the_synthesizer() -> None:
    """**The T3.4 defect, at its cause.** `InvestigationResult.findings` keyed on specialist
    name, so a dict comprehension over the runs kept the last one - and T3.4's three `changes`
    dispatches collapsed to quoteservice, which was empty. The shippingservice change record
    that named the fault outright never reached the synthesizer at all, and the verdict's claim
    that it had never been queried was accurate about what it was shown.

    Two rounds, three services, one specialist. All three have to arrive, each labelled with
    the service it was about - a brief that says `[changes]` three times is a brief in which
    the question "which service?" has no answer.
    """
    round_one = plan_reply(
        [{"specialist": "changes", "service": "cartservice", "question": "q", "reason": "r"}], []
    )
    round_two = plan_reply(
        [
            {"specialist": "changes", "service": "frontend", "question": "q", "reason": "r"},
            {"specialist": "changes", "service": "checkoutservice", "question": "q", "reason": "r"},
        ],
        [],
    )
    model = ScriptedModel(
        {
            "planner": [round_one, round_two],
            "synthesizer": [VERDICT_REPLY],
            "scribe": [draft_reply([])],
        }
    )
    engine, _ = full_engine(model, Budget(max_dispatch_rounds=2))
    result = engine.run("incident-12", triage_of("cartservice"), ANCHOR)

    assert [run.service for run in result.runs] == ["cartservice", "frontend", "checkoutservice"]

    brief = next(call for call in model.calls if call.role == "synthesizer").messages[0]["content"]
    for service in ("cartservice", "frontend", "checkoutservice"):
        assert f"changes on {service}" in brief, f"{service}'s dispatch never reached the brief"
    for run in result.runs:
        assert run.result.id in brief, "each dispatch is addressable by the id that produced it"


def test_the_synthesizer_brief_indexes_every_dispatch_before_the_detail() -> None:
    """What was queried is stated before what was found, so a verdict cannot reason about the
    shape of the investigation from a scan of findings alone."""
    model = ScriptedModel(
        {"planner": [ONE_DISPATCH], "synthesizer": [VERDICT_REPLY], "scribe": [draft_reply([])]}
    )
    engine, _ = full_engine(model, Budget(max_dispatch_rounds=1))
    engine.run("incident-13", triage_of("cartservice"), ANCHOR)

    brief = next(call for call in model.calls if call.role == "synthesizer").messages[0]["content"]
    assert brief.index("Dispatches executed") < brief.index("Specialist findings in full")


def test_a_verdict_contradicting_its_own_trajectory_is_no_longer_flagged() -> None:
    """**Retired at T4.3**, on a live ledger of 0 true positives and 4 false positives.

    This test used to assert the flag reached `result.flags`. It now asserts the opposite, and
    it is kept rather than deleted so the retirement is visible at the place the behaviour
    changed. The verdict text is still never edited - that was never the checker's doing.
    See `faultline.agents.grounding` and ADR-0021's addendum.
    """
    denial = json.dumps(
        {
            "root_cause": "something went wrong",
            "fault_class": "unknown",
            "remediation_class": "none",
            "confidence": "low",
            "evidence": [],
            "reasoning": "No change history has been queried for cartservice at all.",
            "open_questions": [],
        }
    )
    model = ScriptedModel(
        {"planner": [ONE_DISPATCH], "synthesizer": [denial], "scribe": [draft_reply([])]}
    )
    engine, _ = full_engine(model, Budget(max_dispatch_rounds=1))
    result = engine.run("incident-14", triage_of("cartservice"), ANCHOR)

    assert result.verdict is not None
    assert "No change history has been queried" in result.verdict.reasoning, "not stripped"
    assert result.contradictions == [], "the check is retired and emits nothing"
    assert not [f for f in result.flags if f.startswith("contradiction:")]


# --- the dispatch contract (T3.4c) --------------------------------------------

# Verbatim from trajectory 6b9715de-f684-4352-9739-bbdeeb3607df, T3.4b's live run. Both were
# accepted by the contract, reached the tool layer, and produced selectors that cannot match.
T34B_COMMA_LIST = "paymentservice, currencyservice, cartservice, productcatalogservice"
T34B_PROSE_LIST = (
    "checkoutservice and its direct dependencies (paymentservice, currencyservice, "
    "cartservice, productcatalogservice, frontend)"
)


def plan_naming(service: str) -> str:
    return plan_reply(
        [{"specialist": "metrics", "service": service, "question": "q", "reason": "r"}],
        [{"specialist": "logs", "reason": "later"}],
    )


def test_the_comma_list_from_t34b_is_rejected_and_the_reask_says_what_is_legal() -> None:
    """**The T3.4b defect, verbatim.** Four service names in one `service` field became a PromQL
    label value that cannot match any `service_name`, so the query returned no series at all -
    not even a zero-valued denominator - and the specialist reported an empty result.

    ADR-0019's empty-is-not-error principle covers a well-formed query that found nothing. It
    does not cover a selector that cannot match, and reading that emptiness as evidence is the
    defect: it is the one shape of empty that means nothing while looking like the shape that
    means everything.
    """
    model = ScriptedModel({"planner": [plan_naming(T34B_COMMA_LIST), plan_naming("cartservice")]})
    completion = Planner(model).plan(triage_of("cartservice"))

    assert completion.attempts == 2, "rejected, then re-asked once"
    assert completion.value.dispatches[0].service == "cartservice"

    reask = model.calls[1].messages[-1]["content"]
    assert T34B_COMMA_LIST in reask, "the planner is told which value was wrong"
    assert "names more than one service" in reask
    assert "make three dispatches" in reask
    assert "cartservice" in reask and "shippingservice" in reask, "and what is legal"


def test_the_prose_list_from_t34b_is_rejected_too() -> None:
    """The other half of the same run: a `service` field carrying a sentence. It is the same
    error wearing different punctuation, and a check that only looked for commas would pass the
    ones joined by "and"."""
    model = ScriptedModel({"planner": [plan_naming(T34B_PROSE_LIST), plan_naming("frontend")]})
    completion = Planner(model).plan(triage_of("cartservice"))

    assert completion.attempts == 2
    assert "names more than one service" in model.calls[1].messages[-1]["content"]


def test_an_unknown_service_is_rejected_with_the_legal_values() -> None:
    """A name nobody has heard of is a different error from a list, and says so."""
    model = ScriptedModel({"planner": [plan_naming("shoppingcartsvc"), plan_naming("cartservice")]})
    Planner(model).plan(triage_of("cartservice"))

    reask = model.calls[1].messages[-1]["content"]
    assert "is not a service this system knows" in reask
    assert "productcatalogservice" in reask


def test_either_naming_scheme_is_accepted_and_stored_canonically() -> None:
    """`cart-service` and `cartservice` are the same service; `canonical_service` is what says
    so. The contract accepts either and normalises, so everything downstream of the plan sees
    one identity - which is the whole reason that machinery exists (ADR-0008's axis 1)."""
    model = ScriptedModel({"planner": [plan_naming("cart-service")]})
    completion = Planner(model).plan(triage_of("cartservice"))

    assert completion.attempts == 1, "not an error, just the other name"
    assert completion.value.dispatches[0].service == "cartservice"


def test_a_second_illegal_reply_loses_that_dispatch_and_keeps_the_rest() -> None:
    """**Fails the dispatch alone.** Three good dispatches and one bad one is three dispatches'
    worth of evidence; throwing the round away to punish the fourth costs more than the fourth
    was worth. The drop is recorded, never silent."""
    stubborn = plan_reply(
        [
            {"specialist": "metrics", "service": T34B_COMMA_LIST, "question": "q", "reason": "r"},
            {"specialist": "changes", "service": "cartservice", "question": "q", "reason": "r"},
        ],
        [],
    )
    model = ScriptedModel({"planner": [stubborn, stubborn]})
    completion = Planner(model).plan(triage_of("cartservice"))

    assert [d.service for d in completion.value.dispatches] == ["cartservice"]
    assert len(completion.rejected) == 1
    assert T34B_COMMA_LIST in completion.rejected[0]


def test_a_plan_with_nothing_legal_left_still_fails() -> None:
    """Salvage is not leniency. A plan whose every dispatch is illegal after the re-ask has
    nothing to run, and pretending otherwise would hand the loop an empty round."""
    hopeless = plan_naming(T34B_COMMA_LIST)
    model = ScriptedModel({"planner": [hopeless, hopeless]})
    with pytest.raises(SchemaValidationError):
        Planner(model).plan(triage_of("cartservice"))


def test_a_rejected_dispatch_reaches_the_investigations_flags() -> None:
    """It has to arrive where every other kind of incompleteness arrives, or T4.2 cannot see
    that the plan the planner wrote is not the plan that ran."""
    mixed = plan_reply(
        [
            {"specialist": "metrics", "service": T34B_COMMA_LIST, "question": "q", "reason": "r"},
            {"specialist": "changes", "service": "cartservice", "question": "q", "reason": "r"},
        ],
        [],
    )
    model = ScriptedModel(
        {
            "planner": [mixed, mixed],
            "synthesizer": [VERDICT_REPLY],
            "scribe": [draft_reply([])],
        }
    )
    engine, _ = full_engine(model, Budget(max_dispatch_rounds=1))
    result = engine.run("incident-15", triage_of("cartservice"), ANCHOR)

    assert [run.service for run in result.runs] == ["cartservice"]
    flag = next(f for f in result.flags if "more than one service" in f)
    assert flag.startswith("planner produced no valid findings")


# --- the two leak boundaries (T4.2) -------------------------------------------

from faultline.agents.narrative import leaked_words  # noqa: E402

# Verbatim from trajectory 5b5d82e1-f0df-46da-a903-32edbd57fb4a, run 3's "Open questions"
# section. It contains no banned word; `default` contains `fault`, and the substring match
# refused the entire narrative over it.
RUN3_REFUSED_SENTENCE = (
    "No prior value was recorded for the Redis address, so it is genuinely unsettled whether "
    "6380 replaced a working endpoint or was set for the first time over a default."
)


def test_the_sentence_that_cost_run_three_its_narrative_now_renders() -> None:
    """**The guard's first live refusal**, and the diagnosis is not what the error message said.

    The error read `the narrative mentions ['fault']`. The scribe never wrote `fault`: it wrote
    `default`, in a sentence about a Redis port, on a scenario whose entire subject is a port
    that is not the default one. A whole narrative was lost to a substring match on ordinary
    English (`docs/evidence/t4.1-first-scored-run/`).
    """
    assert "fault" not in RUN3_REFUSED_SENTENCE.split(), "the bare word never appears"
    assert "default" in RUN3_REFUSED_SENTENCE

    assert leaked_words(RUN3_REFUSED_SENTENCE) == []


def test_ordinary_incident_english_is_not_a_leak_in_prose_the_agent_composed() -> None:
    """The scribe writes in its own voice from validated findings and cannot see the injector's
    model. `fault` there is a responder writing English, not evidence of anything."""
    for sentence in (
        "The fault domain was wider than the page suggested.",
        "A faulty connection to the datastore, not a faulty service.",
        "Traffic defaulted to the healthy replica.",
    ):
        assert leaked_words(sentence) == [], sentence


def test_harness_vocabulary_is_still_refused_in_prose() -> None:
    """The boundary that did not move. These reveal that the incident was manufactured, or hand
    the reader the classification, and no narrative legitimately needs any of them."""
    assert leaked_words("this scenario was injected by the injector") == [
        "inject",
        "injected",
        "injector",
        "scenario",
    ]
    assert leaked_words("a chaos experiment using pumba and netem") == ["chaos", "netem", "pumba"]
    for label in ("bad_deploy", "bad_config", "dependency_latency", "resource_exhaustion"):
        assert leaked_words(f"the class is {label} here") == [label], label


def test_the_class_labels_stay_banned_because_they_are_the_answer_key() -> None:
    """`ARTIFACTS.md` forbids opening with the diagnosis; naming the class does it in one word.
    This is the half of the old list that had nothing to do with substring accidents."""
    assert leaked_words("This was a bad_deploy.") == ["bad_deploy"]


def test_word_boundaries_do_not_let_a_real_leak_through() -> None:
    """Boundary matching is the fix, and it must not become an escape hatch.

    The two ends are not symmetric on purpose: nothing may precede a term (that is what makes
    `default` safe), but ordinary inflections may follow it (that is what stops `scenarios` and
    `rehearsed` walking straight through).
    """
    assert leaked_words("two scenarios were rehearsed") == ["rehearse", "scenario"]
    assert leaked_words("(injection)") == ["injection"]
    assert leaked_words("chaos, then quiet") == ["chaos"]


def test_the_change_record_guard_is_unchanged_and_still_substring_matched() -> None:
    """The other boundary. That text is rendered from the injector's own model, so any of its
    vocabulary appearing there is evidence the rendering leaked - an over-match costs nothing
    and a miss costs the experiment. `BANNED_VOCABULARY` keeps `fault` and keeps its semantics.
    """
    from faultline.tools.changes import BANNED_VOCABULARY, HARNESS_VOCABULARY, PROSE_VOCABULARY

    assert BANNED_VOCABULARY == HARNESS_VOCABULARY | PROSE_VOCABULARY
    assert sorted(PROSE_VOCABULARY) == ["fault"], "one word moved, and it is visible"
    assert "fault" in BANNED_VOCABULARY and "fault" not in HARNESS_VOCABULARY
    # Substring semantics, as T2.6 built them.
    assert [w for w in BANNED_VOCABULARY if w in "over a default"] == ["fault"]


# --- the taxonomy instruction (T4.5) ------------------------------------------


def test_the_synthesizer_is_taught_the_taxonomy_and_not_the_answers() -> None:
    """**Teaching the taxonomy is legitimate; teaching the answers is contamination.**

    The instruction added at T4.5 defines the four classes from what the label set means. It
    must not name a scenario, a service, or anything else that functions as an answer key -
    ADR-0008 axis 1 is prompt text fitted to the scenarios, and a prompt that says "a memory cap
    on adservice is resource_exhaustion" is that axis in one sentence.
    """
    from faultline.agents.roles import SYNTHESIZER_SYSTEM

    text = SYNTHESIZER_SYSTEM.lower()
    for token in (
        "cart-redis-misconfig",
        "shipping-wrong-image",
        "ad-memory-squeeze",
        "cartservice",
        "adservice",
        "shippingservice",
        "frauddetectionservice",
        "productcatalogservice",
        "redis",
        "pumba",
        "netem",
    ):
        assert token not in text, f"{token} is an answer key, not a definition"


def test_the_taxonomy_instruction_defines_all_four_classes_by_mechanism() -> None:
    """Each class is defined by what the service is doing wrong, not by what act preceded it -
    which is the distinction the first sweep showed the classifier did not have."""
    from faultline.agents.roles import SYNTHESIZER_SYSTEM

    for label in ("resource_exhaustion", "dependency_latency", "bad_deploy", "bad_config"):
        assert f"`{label}`:" in SYNTHESIZER_SYSTEM, label
    assert "evidence for" in SYNTHESIZER_SYSTEM.lower()
    assert "never the class itself" in SYNTHESIZER_SYSTEM


def test_one_specialist_can_be_given_a_larger_bound_than_the_others() -> None:
    """**T4.7's manipulation.** Every budget-exhausted run in the record exhausted the same
    bound - `changes` - because T3.4c made a dispatch name one service, multiplying the
    planner's change-history needs by the blast radius while the bound stayed where it was set
    for a planner that could ask about several services at once.

    Raising one bound has to be possible without raising the rest, or the manipulation changes
    two things and measures neither.
    """
    from faultline.agents.budget import Budget, BudgetState

    state = BudgetState(
        Budget(max_tool_calls_per_specialist=4, per_specialist_tool_calls={"changes": 8})
    )
    for _ in range(8):
        assert state.may_call_tool("changes"), "the override applies"
        state.record_tool_call("changes")
    assert not state.may_call_tool("changes")
    assert "changes tool calls: 8 of 8 used" in (state.exhausted_reason or "")


def test_a_specialist_without_an_override_keeps_the_default_bound() -> None:
    from faultline.agents.budget import Budget, BudgetState

    state = BudgetState(
        Budget(max_tool_calls_per_specialist=4, per_specialist_tool_calls={"changes": 8})
    )
    for _ in range(4):
        state.record_tool_call("metrics")
    assert not state.may_call_tool("metrics")
    assert "metrics tool calls: 4 of 4 used" in (state.exhausted_reason or "")


# --- the evidence-class instruction (T4.12) -----------------------------------
#
# T4.12 added an instruction to PLANNER_SYSTEM teaching that an empty stream is silence
# rather than a bad query, and the two guards that stood here asserted its text and its
# freedom from answer keys. The instruction was measured against dev sweep 3 and reverted:
# it won the one scenario it targeted and cost three others, coverage 6/7 -> 4/7, against a
# floor registered before the run. The guards go with it - a test pinning the wording of a
# prompt that no longer exists is rot, and the evidence for what it did lives in
# evals/runs/SWEEP-2026-08-27-evidence.md rather than in an assertion here.
#
# What the regressions decomposed is recorded in PLAN.md as the next candidate: the
# instruction taught switching vantage but never returning, so the next formulation keeps
# the subject fixed and moves only the evidence class.


# --- the return-to-locus instruction (T4.14) ----------------------------------


def test_the_planner_is_taught_that_silence_changes_the_class_not_the_subject() -> None:
    """T4.12's instruction taught switching vantage and never taught returning: having moved
    outward from a silent stream, nothing brought the planner back to the service it had
    already localized, and the failing-service dispatch count collapsed 3->0, 4->1, 3->0 on
    exactly its three regressions. This formulation separates the two halves.
    """
    import re

    from faultline.agents.roles import PLANNER_SYSTEM

    # The prompt is hard-wrapped, so a phrase that spans a line break would not match a
    # literal search. Normalise whitespace rather than reflowing the prompt to suit a test.
    text = re.sub(r"\s+", " ", PLANNER_SYSTEM.lower())
    assert "silence changes the evidence class, not the subject" in text
    assert "do not put the same question back to it" in text
    # The half T4.12 was missing, which is the whole point of this stamp.
    assert "keeps its claim on your dispatches until its evidence classes are exhausted" in text


def test_the_return_to_locus_instruction_names_no_answers() -> None:
    """Same bar as T4.5's taxonomy instruction and T4.12's. Teaching how to spend dispatches
    is legitimate; naming which service holds the answer in which scenario is ADR-0008 axis 1.
    """
    from faultline.agents.roles import PLANNER_SYSTEM

    text = PLANNER_SYSTEM.lower()
    for token in (
        "product-catalog",
        "productcatalogservice",
        "cart-redis-misconfig",
        "shipping-wrong-image",
        "ad-memory-squeeze",
        "cartservice",
        "adservice",
        "shippingservice",
        "frauddetectionservice",
        "emailservice",
        "featureflagservice",
        "frontend",
        "redis",
        "feature flag",
        "bad_config",
        "bad_deploy",
        "dependency_latency",
        "resource_exhaustion",
    ):
        assert token not in text, f"{token} is an answer key, not an instruction"
