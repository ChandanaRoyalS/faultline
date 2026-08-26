"""The investigation runner: refusal, state write-back, and what a crash leaves behind (T3.5).

Hermetic throughout - a scripted model, the in-memory incident store, the in-memory trajectory
store. The point of this file is the seam T4 needs, and the seam is exactly the part that was
being done by hand in every evidence README up to T3.4c.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from faultline.agents.budget import Budget
from faultline.agents.investigation import Investigation
from faultline.agents.roles import Planner, Scribe, Synthesizer, build_specialists
from faultline.agents.runner import (
    Exit,
    NotInvestigableError,
    investigable,
    run_investigation,
    write_outputs,
)
from faultline.agents.trajectory import InMemoryTrajectoryStore
from faultline.agents.triage import Triage
from faultline.context.catalog import ServiceCatalog
from faultline.context.settings import ContextSettings
from faultline.orchestrator.models import Episode, Incident, IncidentState, Severity
from faultline.orchestrator.store import InMemoryIncidentStore
from faultline.tools.changelog import InMemoryChangeLog
from faultline.tools.settings import ToolSettings
from faultline.tools.tools import Tools
from tests.test_roles import (
    ONE_DISPATCH,
    VERDICT_REPLY,
    ScriptedModel,
    draft_reply,
)

ANCHOR = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def incident_in(state: IncidentState) -> Incident:
    incident = Incident(state=state, opened_at=ANCHOR, last_activity_at=ANCHOR)
    incident.episodes["e0"] = Episode(
        episode_key="e0",
        fingerprint="f0",
        service="cartservice",
        severity=Severity.CRITICAL,
        alertname="ServiceHighErrorRate",
        starts_at=ANCHOR,
        attached_at=ANCHOR,
    )
    return incident


def engine_over(model: ScriptedModel) -> tuple[Investigation, InMemoryTrajectoryStore]:
    trajectories = InMemoryTrajectoryStore()
    engine = Investigation(
        planner=Planner(model),
        specialists=build_specialists(Tools(ToolSettings(), changes=InMemoryChangeLog()), model),
        store=trajectories,
        model=model,
        budget=Budget(max_dispatch_rounds=1),
        synthesizer=Synthesizer(model),
        scribe=Scribe(model),
    )
    return engine, trajectories


def healthy_model() -> ScriptedModel:
    return ScriptedModel(
        {
            "planner": [ONE_DISPATCH],
            "synthesizer": [VERDICT_REPLY],
            "scribe": [draft_reply([])],
        }
    )


def triage_for(incident: Incident) -> object:
    return Triage(ServiceCatalog.from_snapshot(), ContextSettings().hop_radius).run(incident)


# --- refusal -------------------------------------------------------------------


@pytest.mark.parametrize(
    "state",
    [
        IncidentState.OPEN,
        IncidentState.QUEUED,
        IncidentState.PLANNING,
        IncidentState.INVESTIGATING,
        IncidentState.SYNTHESIZING,
        IncidentState.RESOLVED,
        IncidentState.FAILED,
    ],
)
def test_an_incident_the_machine_does_not_investigate_is_refused(state: IncidentState) -> None:
    """**Refused before any model call**, because the cheap check has to come first.

    `TRIAGING` is the only state `ALLOWED` lets `PLANNING` be entered from, so it is the only
    door into the agent lifecycle - and that is the machine's answer rather than a rule invented
    in the runner.
    """
    store = InMemoryIncidentStore()
    incident = incident_in(state)
    store.save(incident)

    with pytest.raises(NotInvestigableError, match=state.value):
        investigable(store, incident.id)


def test_an_incident_that_does_not_exist_is_refused_by_id() -> None:
    with pytest.raises(NotInvestigableError, match="no incident"):
        investigable(InMemoryIncidentStore(), "not-a-real-id")


def test_triaging_is_accepted() -> None:
    store = InMemoryIncidentStore()
    incident = incident_in(IncidentState.TRIAGING)
    store.save(incident)

    assert investigable(store, incident.id) is incident


# --- state write-back ----------------------------------------------------------


def test_a_completed_investigation_walks_the_agent_driven_states() -> None:
    """**The seam T4 needs.** Every evidence README up to T3.4c ends with the incident stuck in
    `triaging`, because nothing wrote the state back. The runner is what ADR-0016's
    `record_agent_outcome` stub was waiting for."""
    store = InMemoryIncidentStore()
    incident = incident_in(IncidentState.TRIAGING)
    store.save(incident)
    engine, _ = engine_over(healthy_model())

    report = run_investigation(store, incident, engine, triage_for(incident), ANCHOR)

    assert report.states == ("triaging", "planning", "investigating", "synthesizing")
    assert store.get(incident.id) is not None
    assert incident.state is IncidentState.SYNTHESIZING
    assert report.exit_code is Exit.CLEAN


def test_it_stops_at_synthesizing_and_does_not_claim_a_proposal() -> None:
    """`PROPOSING` means a remediation proposal exists, and the proposer is the one role of the
    nine nobody has built. An incident parked in `SYNTHESIZING` says what happened and claims
    nothing more."""
    store = InMemoryIncidentStore()
    incident = incident_in(IncidentState.TRIAGING)
    store.save(incident)
    engine, _ = engine_over(healthy_model())

    run_investigation(store, incident, engine, triage_for(incident), ANCHOR)

    assert incident.state is not IncidentState.PROPOSING


def test_the_trajectory_id_is_attached_to_the_incident() -> None:
    """A state saying an investigation happened is not much use without the record of what it
    did. This is the join T4.2 scores against."""
    store = InMemoryIncidentStore()
    incident = incident_in(IncidentState.TRIAGING)
    store.save(incident)
    engine, trajectories = engine_over(healthy_model())

    report = run_investigation(store, incident, engine, triage_for(incident), ANCHOR)

    assert incident.investigation_id == report.trajectory_id
    assert trajectories.get(report.trajectory_id) is not None


def test_a_flagged_verdict_is_still_a_completed_investigation_with_its_own_exit_code() -> None:
    """ADR-0020 §5: exhaustion produces a flagged verdict, not a `FAILED` incident, because a
    partial diagnosis is scoreable. The state has to agree with that, and the exit code has to
    let a sweep count them without parsing prose."""
    store = InMemoryIncidentStore()
    incident = incident_in(IncidentState.TRIAGING)
    store.save(incident)
    model = healthy_model()
    engine, _ = engine_over(model)
    engine._budget = Budget(max_dispatch_rounds=1, max_tool_calls_per_specialist=0)

    report = run_investigation(store, incident, engine, triage_for(incident), ANCHOR)

    assert report.result is not None and report.result.flags
    assert incident.state is IncidentState.SYNTHESIZING, "flagged is not failed"
    assert report.exit_code is Exit.FLAGGED


# --- failure honesty -----------------------------------------------------------


class ExplodingModel(ScriptedModel):
    """Fails on a named role, after the earlier ones have already written to the trajectory."""

    def __init__(self, replies: dict[str, list[str]], explode_on: str) -> None:
        super().__init__(replies)
        self._explode_on = explode_on

    def complete(self, request: object) -> object:
        role = getattr(request, "role", "")
        if role == self._explode_on:
            raise RuntimeError("the model boundary fell over")
        return super().complete(request)  # type: ignore[arg-type]


def test_a_crash_mid_investigation_leaves_a_readable_partial_trajectory() -> None:
    """A run that dies after three specialists is three specialists' worth of evidence. The
    trajectory is written step by step for exactly this reason, and the runner must not lose it
    by letting the exception escape the command."""
    store = InMemoryIncidentStore()
    incident = incident_in(IncidentState.TRIAGING)
    store.save(incident)
    model = ExplodingModel(
        {"planner": [ONE_DISPATCH], "synthesizer": [VERDICT_REPLY]}, explode_on="synthesizer"
    )
    engine, trajectories = engine_over(model)

    report = run_investigation(store, incident, engine, triage_for(incident), ANCHOR)

    assert report.error is not None and "RuntimeError" in report.error
    assert report.exit_code is Exit.NO_VERDICT

    saved = trajectories.trajectories
    assert len(saved) == 1, "the trajectory was persisted despite the crash"
    steps = next(iter(saved.values())).steps
    assert [step.role for step in steps][:2] == ["planner", "changes"]
    assert any(step.payload.get("findings") for step in steps), "the specialist's work survived"


def test_a_crash_after_work_leaves_the_incident_failed_rather_than_stranded() -> None:
    """`FAILED` is terminal and `INVESTIGABLE` is `{TRIAGING}`, so an incident left in
    `PLANNING` by a crash could never be picked up again and nothing would say why. Failing it
    explicitly is the honest end - and the partial trajectory is attached, so the record of what
    it did get to survives the state that says it stopped."""
    store = InMemoryIncidentStore()
    incident = incident_in(IncidentState.TRIAGING)
    store.save(incident)
    model = ExplodingModel(
        {"planner": [ONE_DISPATCH], "synthesizer": [VERDICT_REPLY]}, explode_on="synthesizer"
    )
    engine, _ = engine_over(model)

    report = run_investigation(store, incident, engine, triage_for(incident), ANCHOR)

    assert incident.state is IncidentState.FAILED
    assert report.states == ("triaging", "failed")
    assert report.trajectory_id is not None, "the partial record is named"
    with pytest.raises(NotInvestigableError, match="terminal"):
        investigable(store, incident.id)


def test_a_failure_before_anything_ran_leaves_the_incident_where_it_was() -> None:
    """**Found by T3.5's own smoke**, with a `ModuleNotFoundError` for an optional extra. The
    exception raised before the first model call, the runner moved the incident to `FAILED`, and
    ADR-0016 makes that terminal - so one missing dependency permanently retired a live incident
    that nothing had investigated.

    A failed *start* is not a failed investigation. Nothing about the incident changed, so
    nothing about its state should, and the next attempt finds it exactly where it was.
    """
    store = InMemoryIncidentStore()
    incident = incident_in(IncidentState.TRIAGING)
    store.save(incident)
    model = ExplodingModel({"planner": [ONE_DISPATCH]}, explode_on="planner")
    engine, trajectories = engine_over(model)

    report = run_investigation(store, incident, engine, triage_for(incident), ANCHOR)

    assert incident.state is IncidentState.TRIAGING
    assert report.states == ("triaging",)
    assert report.error is not None and report.error.startswith("did not start")
    assert report.exit_code is Exit.NO_VERDICT, "it still failed, and says so"
    assert trajectories.trajectories == {}, "an empty trajectory is not worth a row"
    assert investigable(store, incident.id) is incident, "retryable"


# --- outputs -------------------------------------------------------------------


def test_the_verdict_and_narrative_are_written_as_files(tmp_path: Path) -> None:
    """T4.2 reads the JSON, a responder reads the markdown. Writing only one of them makes the
    other a parsing exercise."""
    store = InMemoryIncidentStore()
    incident = incident_in(IncidentState.TRIAGING)
    store.save(incident)
    engine, _ = engine_over(healthy_model())
    report = run_investigation(store, incident, engine, triage_for(incident), ANCHOR)

    written = write_outputs(report, tmp_path / "out")

    assert len(written) == 2
    payload = json.loads((tmp_path / "out" / f"{incident.id}-verdict.json").read_text())
    assert payload["trajectory_id"] == report.trajectory_id
    assert payload["states"] == list(report.states)
    assert payload["verdict"]["fault_class"] == "bad_config"
    assert (tmp_path / "out" / f"{incident.id}-narrative.md").read_text().strip()
