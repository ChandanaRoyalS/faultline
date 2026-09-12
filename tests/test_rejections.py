"""The rejection ledger, the machine's rejection, and the loop back to an investigation (T6.3).

`evals/runs/PREREGISTRATION-T6.3.md` §3 lists what the free half of this task has to prove. These
are the items that need no surface: the reason is required, the ledger is a ledger, a rejected
incident is investigable again, the cap holds, and a token minted before the rejection is refused
after it. The surface's own tests arrive with the surface.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from faultline.agents.runner import NotInvestigableError, investigable, latest_rejection
from faultline.orchestrator import machine
from faultline.orchestrator.models import Episode, Incident, IncidentState, Severity
from faultline.orchestrator.rejections import (
    REASON_LIMIT,
    InMemoryRejectionStore,
    Rejection,
    clean_reason,
)
from faultline.orchestrator.runner import InvestigationRunner
from faultline.orchestrator.store import InMemoryIncidentStore

ANCHOR = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)


def incident_in(state: IncidentState, identifier: str = "incident-1") -> Incident:
    incident = Incident(id=identifier, opened_at=ANCHOR, last_activity_at=ANCHOR)
    incident.episodes["e0"] = Episode(
        episode_key="e0",
        fingerprint="f0",
        alertname="CartLatency",
        service="cartservice",
        severity=Severity.WARNING,
        starts_at=ANCHOR,
        attached_at=ANCHOR,
    )
    incident.state = state
    return incident


# --- the reason is required ---------------------------------------------------


def test_a_reason_of_whitespace_is_not_a_reason() -> None:
    """T2.3's *"reason required"*, enforced in one place so the route, the CLI and the machine
    cannot disagree about what empty means."""
    for empty in ("", "   ", "\n\t "):
        with pytest.raises(ValueError, match="needs a reason"):
            clean_reason(empty)


def test_a_very_long_reason_is_truncated_rather_than_refused() -> None:
    """Losing the tail of a long explanation is better than losing the rejection - and a reason
    that could crowd out the allowlist in the brief is a reason that has stopped being one."""
    cleaned = clean_reason("x" * (REASON_LIMIT * 2))

    assert len(cleaned) == REASON_LIMIT
    assert cleaned.endswith("truncated]")


def test_a_reasonless_rejection_moves_nothing() -> None:
    """Prediction 3. The machine refuses before the transition, so an incident cannot reach
    REJECTED with nothing to re-investigate with."""
    incident = incident_in(IncidentState.AWAITING_APPROVAL)

    with pytest.raises(ValueError):
        machine.record_rejection(incident, "  ")

    assert incident.state is IncidentState.AWAITING_APPROVAL


# --- where a rejection may arrive from ----------------------------------------


@pytest.mark.parametrize(
    "state",
    [IncidentState.PROPOSING, IncidentState.SYNTHESIZING, IncidentState.AWAITING_APPROVAL],
)
def test_a_proposal_can_be_rejected_from_the_three_states_the_table_allows(
    state: IncidentState,
) -> None:
    incident = incident_in(state)

    cleaned = machine.record_rejection(incident, "  the latency is on redis-cart  ")

    assert incident.state is IncidentState.REJECTED
    assert cleaned == "the latency is on redis-cart", "stored stripped, as it will be shown"


def test_an_executing_incident_cannot_be_rejected() -> None:
    """The rule lives in the machine rather than at the route, on ADR-0038 Addendum 2's lesson:
    a rule enforced only by whichever layer happens to be asked is a rule about that layer."""
    incident = incident_in(IncidentState.EXECUTING)

    with pytest.raises(machine.TransitionError, match="can be rejected from"):
        machine.record_rejection(incident, "too late")

    assert incident.state is IncidentState.EXECUTING


# --- the ledger ---------------------------------------------------------------


def test_the_ledger_keeps_every_rejection_and_hands_back_the_latest() -> None:
    """A column would hold the most recent reason and lose the one before it. The second
    rejection of an incident is the interesting one: it says the re-investigation did not help."""
    store = InMemoryRejectionStore()
    store.append(Rejection(incident_id="i1", reason="first", caller="chandana"))
    store.append(Rejection(incident_id="i1", reason="second", caller="chandana"))
    store.append(Rejection(incident_id="i2", reason="other", caller="chandana"))

    assert [r.reason for r in store.for_incident("i1")] == ["first", "second"]
    assert store.count("i1") == 2
    assert store.latest("i1") is not None and store.latest("i1").reason == "second"
    assert store.latest("i3") is None


def test_the_re_investigation_is_told_the_latest_rejection_and_no_others() -> None:
    """An agent handed three reasons is being asked to satisfy a committee; the earlier ones are
    already answered by the proposals that followed them. The history stays in the ledger."""
    store = InMemoryRejectionStore()
    store.append(Rejection(incident_id="i1", reason="first", caller="c"))
    store.append(
        Rejection(
            incident_id="i1",
            reason="second",
            caller="c",
            action_id="restart_service",
            target="cartservice",
        )
    )

    told = latest_rejection(store, "i1")

    assert told is not None
    assert told.reason == "second"
    assert (told.action_id, told.target) == ("restart_service", "cartservice")
    assert latest_rejection(store, "never-rejected") is None


# --- the loop back to an investigation ----------------------------------------


def test_a_rejected_incident_is_investigable_again() -> None:
    """`REJECTED -> PLANNING` has been in ADR-0016's table since Phase 2 with nothing able to
    walk it, because `INVESTIGABLE` was `{TRIAGING}`. It is the second door now, and it is the
    machine's answer rather than a choice: those are the two states `PLANNING` is entered from."""
    store = InMemoryIncidentStore()
    incident = incident_in(IncidentState.REJECTED)
    store.incidents[incident.id] = incident

    assert set(machine.INVESTIGABLE) == {IncidentState.TRIAGING, IncidentState.REJECTED}
    assert investigable(store, incident.id) is incident
    assert IncidentState.PLANNING in machine.ALLOWED[IncidentState.REJECTED]


def test_an_executing_incident_is_still_not_investigable() -> None:
    store = InMemoryIncidentStore()
    incident = incident_in(IncidentState.EXECUTING)
    store.incidents[incident.id] = incident

    with pytest.raises(NotInvestigableError, match="investigates from"):
        investigable(store, incident.id)


def runner(
    store: InMemoryIncidentStore,
    rejections: InMemoryRejectionStore | None,
    *,
    max_rejections: int = 2,
) -> InvestigationRunner:
    return InvestigationRunner(
        store,
        settle=timedelta(minutes=1),
        command=["faultline-investigate"],
        run=lambda command: 0,
        now=lambda: ANCHOR + timedelta(minutes=30),
        rejections=rejections,
        max_rejections=max_rejections,
    )


def test_a_rejected_incident_is_due_immediately_and_with_no_settle_window() -> None:
    """The settle window exists so an incident's alerts stop arriving before an agent reads
    them. A rejection arrives long after that; what it waited on was a human, who has acted."""
    store = InMemoryIncidentStore()
    incident = incident_in(IncidentState.REJECTED)
    incident.opened_at = ANCHOR + timedelta(minutes=29, seconds=59)
    store.incidents[incident.id] = incident
    rejections = InMemoryRejectionStore()
    rejections.append(Rejection(incident_id=incident.id, reason="wrong service", caller="c"))

    assert [i.id for i in runner(store, rejections).due()] == [incident.id]


def test_the_cap_stops_the_loop_and_leaves_the_incident_rejected() -> None:
    """Prediction 5. Two rejections, then the incident stays where it is - and it keeps holding
    a cap slot (`INVESTIGATING_STATES` includes REJECTED), so a loop cannot quietly consume the
    world's investigation budget while it spins."""
    store = InMemoryIncidentStore()
    incident = incident_in(IncidentState.REJECTED)
    store.incidents[incident.id] = incident
    rejections = InMemoryRejectionStore()
    for _ in range(2):
        rejections.append(Rejection(incident_id=incident.id, reason="no", caller="c"))

    assert runner(store, rejections).due() == []
    assert incident.state is IncidentState.REJECTED
    assert incident.holds_a_slot


def test_without_a_ledger_nothing_is_re_investigated() -> None:
    """A loop that cannot count its own turns is a loop that does not stop, and this one spends
    a model call per turn. The runner without a rejection store re-investigates nothing at all
    rather than re-investigating forever - which is what a default of "no cap" would mean."""
    store = InMemoryIncidentStore()
    incident = incident_in(IncidentState.REJECTED)
    store.incidents[incident.id] = incident

    assert runner(store, None).due() == []


def test_a_new_rejection_gives_the_incident_a_fresh_attempt_budget() -> None:
    """`attempts` counts runs that may have died before their first transition, so a broken
    incident is not billed forever. It is not a budget for how many times an incident may
    legitimately be investigated - and without the reset, an incident whose first investigation
    used its two attempts could never be re-investigated at all, silently."""
    store = InMemoryIncidentStore()
    incident = incident_in(IncidentState.REJECTED)
    store.incidents[incident.id] = incident
    rejections = InMemoryRejectionStore()
    rejections.append(Rejection(incident_id=incident.id, reason="first", caller="c"))
    loop = runner(store, rejections)
    loop.attempts[incident.id] = 2  # what the first investigation spent

    assert [i.id for i in loop.due()] == [incident.id]
    assert loop.attempts.get(incident.id, 0) == 0

    # And the ordinary two-attempt rule then applies to the new round: a re-investigation that
    # leaves the incident REJECTED is a run that died before its first transition, and it gets the
    # same second chance any other does - then no more, because the third would bill forever.
    loop.run_once()
    assert [i.id for i in loop.due()] == [incident.id]
    loop.run_once()
    assert loop.due() == []


def test_the_ordinary_triaging_path_is_unchanged() -> None:
    """The settle window still applies to an incident nobody has rejected."""
    store = InMemoryIncidentStore()
    fresh = incident_in(IncidentState.TRIAGING, "fresh")
    fresh.opened_at = ANCHOR + timedelta(minutes=29, seconds=59)
    settled = incident_in(IncidentState.TRIAGING, "settled")
    store.incidents[fresh.id] = fresh
    store.incidents[settled.id] = settled

    assert [i.id for i in runner(store, InMemoryRejectionStore()).due()] == ["settled"]
