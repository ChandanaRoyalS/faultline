"""The approve / reject / acknowledge routes (T6.3).

`evals/runs/PREREGISTRATION-T6.3.md` §3, the items that need a surface: a reasonless rejection is
refused and nothing moves; an unacknowledged critical incident cannot be approved and **no token is
minted**; the caller in the ledger is the authenticated username and not something a body claimed;
and the approval path is the same `approve()` the terminal calls rather than a second copy of it.

The executor is a fake here. What the real one does with a token is `tests/test_executor.py`'s
subject and was measured on a live world at T6.2; what this file is about is whether the surface
hands it the right token, on behalf of the right person, and only when it should.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from faultline.agents.trajectory import (
    InMemoryTrajectoryStore,
    StepKind,
    Trajectory,
    TrajectoryStep,
)
from faultline.api import approvals
from faultline.context.allowlist import load_allowlist
from faultline.executor.audit import InMemoryAuditStore
from faultline.executor.settings import ExecutorSettings
from faultline.orchestrator.acknowledgements import InMemoryAcknowledgementStore
from faultline.orchestrator.models import Episode, Incident, IncidentState, Severity
from faultline.orchestrator.rejections import InMemoryRejectionStore
from faultline.orchestrator.store import InMemoryIncidentStore

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
KEY = "0123456789abcdef0123456789abcdef"
WHO = "chandana"

PROPOSAL = {
    "action_id": "rollback_image",
    "target": "shippingservice",
    "remediation_class": "image_rollback",
    "confirm_within_seconds": 300,
    "expected_effect": "errors return to baseline",
    "if_wrong": "they do not",
    "risk": "a restart",
    "blast_radius": "one service",
    "rests_on": [],
}


def incident(
    state: IncidentState = IncidentState.PROPOSING,
    severity: Severity = Severity.WARNING,
    service: str = "shippingservice",
) -> Incident:
    made = Incident(state=state, opened_at=NOW - timedelta(minutes=10))
    made.episodes["ep1"] = Episode(
        episode_key="ep1",
        fingerprint="fp1",
        service=service,
        severity=severity,
        alertname="ServiceHighErrorRate",
        starts_at=NOW - timedelta(minutes=10),
        attached_at=NOW - timedelta(minutes=10),
    )
    return made


def trajectory_for(made: Incident, proposal: dict[str, Any] | None = None) -> Trajectory:
    trajectory = Trajectory(incident_id=made.id, model="fake", effort="medium", started_at=NOW)
    trajectory.add(
        TrajectoryStep(
            seq=7,
            kind=StepKind.PROPOSAL,
            role="proposer",
            at=NOW,
            payload={"proposal": proposal if proposal is not None else PROPOSAL, "accepted": True},
        )
    )
    return trajectory


class FakeExecutor:
    """Records what it was handed. The real one is a different container over HTTP."""

    def __init__(self, outcome: str = "executed") -> None:
        self.calls: list[tuple[str, str]] = []
        self._outcome = outcome

    def execute(self, token: str, *, caller: str) -> dict[str, Any]:
        self.calls.append((token, caller))
        return {"outcome": self._outcome, "reason": "", "caller": caller}


class Harness:
    def __init__(self, made: Incident, with_proposal: bool = True) -> None:
        self.incidents = InMemoryIncidentStore()
        self.incidents.save(made)
        self.incident = made
        self.trajectories = InMemoryTrajectoryStore()
        if with_proposal:
            self.trajectories.save(trajectory_for(made))
        self.audit = InMemoryAuditStore()
        self.rejections = InMemoryRejectionStore()
        self.acknowledgements = InMemoryAcknowledgementStore()
        self.executor = FakeExecutor()
        app = FastAPI()
        app.include_router(
            approvals.build(
                incidents=self.incidents,
                trajectories=self.trajectories,
                audit=self.audit,
                rejections=self.rejections,
                acknowledgements=self.acknowledgements,
                catalog=load_allowlist(),
                settings=ExecutorSettings(token_key=KEY),
                executor=self.executor,
                # The real caller is `auth.guard()`'s dependency, which returns the username it
                # verified. Here it is a stub returning the same shape - a string - so the test
                # exercises the route's use of it rather than basic auth, which `test_api_app`
                # already covers.
                caller=_caller(WHO),
            )
        )
        self.client = TestClient(app)

    def path(self, action: str) -> str:
        return f"/api/v1/incidents/{self.incident.id}/{action}"


def _caller(who: str) -> Any:
    from fastapi import Depends

    return Depends(lambda: who)


# --- reject -------------------------------------------------------------------


def test_a_rejection_records_the_reason_moves_the_incident_and_names_the_proposal() -> None:
    harness = Harness(incident(IncidentState.AWAITING_APPROVAL))

    response = harness.client.post(
        harness.path("reject"), json={"reason": "the latency is on redis-cart's interface"}
    )

    assert response.status_code == 200
    assert response.json()["state"] == "rejected"
    assert harness.incident.state is IncidentState.REJECTED
    [row] = harness.rejections.for_incident(harness.incident.id)
    assert row.reason == "the latency is on redis-cart's interface"
    assert row.caller == WHO, "the ledger names the credential's user, not a body's claim"
    assert row.action_id == "rollback_image" and row.target == "shippingservice"
    assert row.proposal_id.endswith("#7"), "the proposal the approver was looking at"


def test_a_reasonless_rejection_is_refused_and_nothing_moves() -> None:
    """Prediction 3. The route refuses, the machine refuses, and the ledger stays empty - three
    layers because the reason is the only input a re-investigation has."""
    harness = Harness(incident(IncidentState.AWAITING_APPROVAL))

    blank = harness.client.post(harness.path("reject"), json={"reason": "   "})
    missing = harness.client.post(harness.path("reject"), json={})

    assert blank.status_code == 400
    assert missing.status_code == 422, "the contract refuses an absent reason before the route"
    assert harness.incident.state is IncidentState.AWAITING_APPROVAL
    assert harness.rejections.count(harness.incident.id) == 0


def test_an_executing_incident_cannot_be_rejected_from_the_surface() -> None:
    harness = Harness(incident(IncidentState.EXECUTING))

    response = harness.client.post(harness.path("reject"), json={"reason": "too late"})

    assert response.status_code == 409
    assert "can be rejected from" in response.json()["detail"]
    assert harness.rejections.count(harness.incident.id) == 0


def test_an_incident_with_no_resolvable_proposal_can_still_be_rejected() -> None:
    """The operator saw something on the screen and said no to it. The row records what could be
    established; the reason is the part a re-investigation needs."""
    harness = Harness(incident(IncidentState.SYNTHESIZING), with_proposal=False)

    response = harness.client.post(harness.path("reject"), json={"reason": "not this service"})

    assert response.status_code == 200
    [row] = harness.rejections.for_incident(harness.incident.id)
    assert row.reason == "not this service" and row.action_id == ""


# --- approve ------------------------------------------------------------------


def test_approving_mints_a_token_executes_it_and_records_who() -> None:
    harness = Harness(incident(IncidentState.PROPOSING))

    response = harness.client.post(harness.path("approve"))

    assert response.status_code == 200
    body = response.json()
    assert body["approved"]["outcome"] == "approved"
    assert body["approved"]["caller"] == WHO
    assert body["executed"]["outcome"] == "executed"
    # **`AWAITING_APPROVAL`, not `EXECUTING`, and that is right.** The approval moves the incident
    # that far; `EXECUTING` is written by the executor, in the executor's process, against the same
    # database - so the surface's in-memory copy is one transition behind on purpose and the page
    # catches up on its next poll. A surface that advanced it here would be claiming an execution
    # it had not seen, which is the thing ADR-0038 §5's *record before advance* exists to prevent.
    assert harness.incident.state is IncidentState.AWAITING_APPROVAL
    [(token, caller)] = harness.executor.calls
    assert caller == WHO
    assert token and token not in response.text, "the token never reaches the browser"


def test_the_approval_goes_through_the_same_function_the_terminal_calls() -> None:
    """Not a second implementation. `executor.cli.approve` is what mints, what writes the
    `approved` row, and what moves the incident - so a rule added there (one action per incident,
    ADR-0038 Addendum 2) is a rule the button obeys without being told."""
    import faultline.executor.cli as cli

    harness = Harness(incident(IncidentState.PROPOSING))
    seen: list[str] = []
    original = cli.approve

    def spy(**kwargs: Any) -> Any:
        seen.append(kwargs["caller"])
        return original(**kwargs)

    cli.approve = spy  # type: ignore[assignment]
    try:
        assert harness.client.post(harness.path("approve")).status_code == 200
    finally:
        cli.approve = original  # type: ignore[assignment]

    assert seen == [WHO]


def test_a_rejected_incident_cannot_be_approved_from_the_surface() -> None:
    harness = Harness(incident(IncidentState.AWAITING_APPROVAL))
    harness.client.post(harness.path("reject"), json={"reason": "wrong service"})

    response = harness.client.post(harness.path("approve"))

    assert response.status_code == 409
    assert "awaiting re-investigation" in response.json()["detail"]
    assert harness.executor.calls == []


def test_approving_a_missing_incident_is_a_404() -> None:
    harness = Harness(incident())

    assert harness.client.post("/api/v1/incidents/nope/approve").status_code == 404


# --- the sev-1 acknowledgment gate --------------------------------------------


def test_an_unacknowledged_critical_incident_cannot_be_approved_and_mints_nothing() -> None:
    """Prediction 4, and the *mints nothing* half is the point. The gate refuses **before**
    `approve()` is called, so there is no token in existence for a click the gate stopped and no
    `approved` row in the ledger claiming one was given."""
    harness = Harness(incident(IncidentState.PROPOSING, Severity.CRITICAL))

    response = harness.client.post(harness.path("approve"))

    assert response.status_code == 409
    assert response.json()["detail"] == approvals.ACK_REQUIRED
    assert harness.audit.rows == []
    assert harness.executor.calls == []
    assert harness.incident.state is IncidentState.PROPOSING


def test_an_acknowledged_critical_incident_approves() -> None:
    harness = Harness(incident(IncidentState.PROPOSING, Severity.CRITICAL))

    acknowledged = harness.client.post(harness.path("acknowledge"), json={"note": "I have it"})
    approved = harness.client.post(harness.path("approve"))

    assert acknowledged.status_code == 200
    assert acknowledged.json()["acknowledged"]["caller"] == WHO
    assert approved.status_code == 200
    assert len(harness.executor.calls) == 1


def test_a_warning_incident_needs_no_acknowledgment() -> None:
    """The gate is on severity 1. Putting it on everything would train an operator to click
    through it, which is the failure mode an acknowledgment exists to avoid."""
    harness = Harness(incident(IncidentState.PROPOSING, Severity.WARNING))

    assert harness.client.post(harness.path("approve")).status_code == 200


def test_the_first_acknowledgment_is_the_gate_and_a_second_changes_nothing() -> None:
    harness = Harness(incident(IncidentState.PROPOSING, Severity.CRITICAL))

    harness.client.post(harness.path("acknowledge"), json={"note": "first"})
    harness.client.post(harness.path("acknowledge"), json={"note": "second"})

    first = harness.acknowledgements.first(harness.incident.id)
    assert first is not None and first.note == "first"
