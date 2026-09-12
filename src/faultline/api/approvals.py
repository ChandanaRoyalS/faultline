"""The approve / reject / acknowledge routes (T6.3).

**This is the first write surface this product has ever had**, and it is a separate module from
`incidents.py` on purpose. That module's docstring says of itself: *"the router never imports a
writer, never opens a transaction, and cannot advance a state machine"* - and that sentence is
worth keeping true of the routes that serve the screen, so the routes that change things live
here, behind the same credential, and `tests/test_executor_boundary.py` holds that
`faultline.api.incidents` still imports no writer and that the investigation runtime imports
neither this module nor the executor.

## What a click does

`POST /api/v1/incidents/{id}/approve` mints a token through `executor.cli.approve` - the same
function the terminal calls, not a second implementation - then presents it to the executor and
returns the audit row. `.../reject` requires a reason, records it in `incident_rejections`, moves
the incident to `REJECTED`, and leaves the orchestrator's runner to re-investigate.
`.../acknowledge` records who is watching a critical incident, which is what the sev-1 gate waits
for.

**One click approves and executes.** The proposal's safety sentence is *"approve this rollback, not
'approve'"*; a surface that minted a token and then waited for a second click would be asking the
approver to confirm the thing they had already confirmed, and would leave a live bearer credential
in a browser between the two.

## The registered escalation

`evals/runs/PREREGISTRATION-T6.3.md` §2.1: **this process holds the minting key.** A compromised
surface can therefore sign a claim for any incident, action and target. What bounds it is not the
key - it is that the executor re-derives everything from its own sources: the action must be in the
catalog and `available`, the target must be inside the incident's recomputed blast radius, the
drift precondition must hold, the token must be unspent, the incident must have no executed action
already and must not be terminal or rejected, and the kill switch must be off. A key-holder can do
what an approver can do, and every attempt is a row naming the caller. A separate minting process
was considered and rejected there, with reasons.

## The caller is the authenticated username

Not a constant. An audit row that says *who approved* is the point of the row, and
`auth.guard()`'s dependency already returns the username it verified - so the identity in the
ledger is the identity the credential proved, rather than one the request body claimed.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from fastapi import APIRouter, Body, HTTPException, status
from pydantic import BaseModel, Field

from faultline.orchestrator import machine
from faultline.orchestrator.acknowledgements import Acknowledgement, AcknowledgementStore
from faultline.orchestrator.models import IncidentState, Severity
from faultline.orchestrator.rejections import REASON_LIMIT, Rejection, RejectionStore

log = logging.getLogger(__name__)

ACK_REQUIRED = (
    "this incident is critical and nobody has acknowledged it; acknowledge it first, then approve"
)
"""Refused **before minting**, so no token exists to be spent and the ledger carries no `approved`
row for a click the gate stopped."""


class Executes(Protocol):
    """What the router needs of the executor: present a token, get the audit row back.

    A protocol rather than an HTTP client type because the deployment's executor is a different
    container and the tests' is a fake, and neither should be able to tell from this module which
    one it is talking to.
    """

    def execute(self, token: str, *, caller: str) -> dict[str, Any]: ...


class RejectBody(BaseModel):
    reason: str = Field(min_length=1, max_length=REASON_LIMIT * 2)
    """Longer than `REASON_LIMIT` is accepted here and truncated by `clean_reason`: the ledger
    decides what a reason is, and a route that refused what the ledger would have stored would be
    a second opinion about the same rule."""


class AcknowledgeBody(BaseModel):
    note: str = Field(default="", max_length=500)


ACK_BODY = Body(default_factory=AcknowledgeBody)
"""Module-level for ruff's B008, which is right about it for the same reason `auth.SCHEME` is."""


def build(
    *,
    incidents: Any,
    trajectories: Any,
    audit: Any,
    rejections: RejectionStore,
    acknowledgements: AcknowledgementStore,
    catalog: Any,
    settings: Any,
    executor: Executes,
    caller: Any,
) -> APIRouter:
    """The write routes.

    `caller` is the `params.Depends` `auth.guard()` returns - the dependency that verified the
    credential and hands back the username it verified. It is used as the default of a `who`
    argument on every route here, so the identity in the ledger is the identity the credential
    proved. It cannot come from a request body, because no route reads one.
    """
    from faultline.executor.cli import ApproveError, _proposal_from_trajectory

    router = APIRouter(prefix="/api/v1/incidents")

    def _incident(incident_id: str) -> Any:
        found = incidents.get(incident_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"no incident {incident_id}")
        return found

    @router.post("/{incident_id}/acknowledge")
    def acknowledge(
        incident_id: str,
        body: AcknowledgeBody = ACK_BODY,
        who: str = caller,
    ) -> dict[str, Any]:
        incident = _incident(incident_id)
        row = Acknowledgement(incident_id=incident.id, caller=who, note=body.note)
        acknowledgements.append(row)
        log.info("incident %s acknowledged by %s", incident.id, who)
        return {"acknowledged": row.as_dict()}

    @router.post("/{incident_id}/reject")
    def reject(
        incident_id: str,
        body: RejectBody,
        who: str = caller,
    ) -> dict[str, Any]:
        """**The ledger is written before the state moves, and the reason is cleaned by the
        machine.** A rejection recorded against an incident that never moved is a puzzle; an
        incident in `REJECTED` with no reason is a re-investigation with nothing to go on, and
        `record_rejection` refuses to produce one."""
        incident = _incident(incident_id)
        proposal_id = action_id = target = ""
        try:
            proposal, proposal_id = _proposal_from_trajectory(trajectories, incident.id)
            action_id = str(proposal.get("action_id") or "")
            target = str(proposal.get("target") or "")
        except ApproveError:
            # A rejection of an incident whose proposal cannot be resolved is still a rejection -
            # the operator saw something on the screen and said no to it. The row records what
            # could be established, and the reason is the part that matters.
            log.info("incident %s rejected with no resolvable proposal", incident.id)
        try:
            cleaned = machine.record_rejection(incident, body.reason)
        except ValueError as refusal:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(refusal)) from refusal
        except machine.TransitionError as refusal:
            raise HTTPException(status.HTTP_409_CONFLICT, str(refusal)) from refusal
        rejections.append(
            Rejection(
                incident_id=incident.id,
                reason=cleaned,
                caller=who,
                proposal_id=proposal_id,
                action_id=action_id,
                target=target,
            )
        )
        incidents.save_investigation_state(incident)
        log.info("incident %s rejected by %s: %s", incident.id, who, cleaned)
        return {"state": incident.state.value, "reason": cleaned}

    @router.post("/{incident_id}/approve")
    def approve_and_execute(
        incident_id: str,
        who: str = caller,
    ) -> dict[str, Any]:
        """Mint, then execute. The gate is checked **before** minting."""
        from faultline.executor.cli import approve as mint_approval

        incident = _incident(incident_id)
        if incident.severity is Severity.CRITICAL and acknowledgements.first(incident.id) is None:
            raise HTTPException(status.HTTP_409_CONFLICT, ACK_REQUIRED)
        if incident.state is IncidentState.REJECTED:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"incident {incident.id} was rejected and is awaiting re-investigation; there is "
                "no proposal here to approve",
            )
        try:
            proposal, proposal_id = _proposal_from_trajectory(trajectories, incident.id)
            token, record = mint_approval(
                incident_id=incident.id,
                incidents=incidents,
                audit=audit,
                settings=settings,
                catalog=catalog,
                proposal=proposal,
                proposal_id=proposal_id,
                caller=who,
            )
        except ApproveError as refusal:
            raise HTTPException(status.HTTP_409_CONFLICT, str(refusal)) from refusal
        # **The token is never returned to the browser.** It is a bearer credential for as long as
        # it is unspent, and the browser has no use for one: the surface that minted it is the
        # surface that presents it, in the same request.
        performed = executor.execute(token, caller=who)
        log.info(
            "incident %s approved by %s: %s -> %s, executor says %s",
            incident.id,
            who,
            record.action_id,
            record.target,
            performed.get("outcome"),
        )
        return {"approved": record.as_dict(), "executed": performed}

    return router
