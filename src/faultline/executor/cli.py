"""`faultline-approve` mints; `faultline-execute` acts (T6.2).

Two commands rather than one, because they are two sides of a boundary: the approver holds the
key and a proposal; the executor holds the key and the world. T6.3's approve / reject surface will
call `approve()` from a button; until then this is how a human says *"this rollback, on this
service, for this incident"* - and the token is the only thing that crosses.

**The token is printed once, to stdout, and nowhere else.** The audit records its id. An operator
who loses it mints another; a log that kept it would be a second copy of a bearer credential.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from faultline.executor.audit import AuditRecord
from faultline.executor.settings import ExecutorSettings
from faultline.executor.tokens import mint


class ApproveError(RuntimeError):
    pass


def _proposal_from_trajectory(trajectories: Any, incident_id: str) -> tuple[dict[str, Any], str]:
    """The incident's own accepted proposal - the newest PROPOSAL step of its newest trajectory.
    `proposal_id` is `<trajectory>#<seq>`, so the audit points at the object the approver read."""
    trajectory = trajectories.latest_for_incident(incident_id)
    if trajectory is None:
        raise ApproveError(f"incident {incident_id} has no trajectory; nothing was proposed")
    for step in reversed(trajectory.steps):
        if step.kind == "proposal" and step.payload.get("accepted", True):
            proposal = step.payload.get("proposal") or {}
            if not proposal.get("action_id"):
                raise ApproveError(
                    f"incident {incident_id}: the proposer abstained "
                    f"(remediation_class={proposal.get('remediation_class')!r}); there is nothing "
                    "to approve"
                )
            return proposal, f"{trajectory.id}#{step.seq}"
    raise ApproveError(f"incident {incident_id}: its trajectory carries no accepted proposal")


def _proposal_from_run(run_dir: Path) -> tuple[dict[str, Any], str]:
    """The operator path (ADR-0016 Addendum 4): a proposal recorded in an earlier run's verdict
    artifact, supplied against a different incident. `proposal_id` is the run directory, which is
    what the pre-registration's repair replay names."""
    verdicts = sorted(run_dir.glob("*-verdict.json"))
    if not verdicts:
        raise ApproveError(f"{run_dir} holds no *-verdict.json")
    payload = json.loads(verdicts[0].read_text())
    proposal = payload.get("proposal") or {}
    if not proposal.get("action_id"):
        raise ApproveError(f"{verdicts[0].name}: the recorded proposal is an abstention")
    return proposal, run_dir.name


def approve(
    *,
    incident_id: str,
    incidents: Any,
    audit: Any,
    settings: ExecutorSettings,
    catalog: Any,
    proposal: dict[str, Any],
    proposal_id: str,
    caller: str,
    now: datetime | None = None,
) -> tuple[str, AuditRecord]:
    """Mint a token for `proposal` against `incident_id`, record the approval, and move the
    incident to `AWAITING_APPROVAL`. Returns the token (print it once) and the audit row."""
    from faultline.orchestrator.machine import (
        ApprovalOutcome,
        is_terminal,
        record_approval_outcome,
    )
    from faultline.orchestrator.models import IncidentState
    from injector.world import canonical_service

    incident = incidents.get(incident_id)
    if incident is None:
        raise ApproveError(f"incident {incident_id} does not exist")
    if is_terminal(incident.state):
        raise ApproveError(
            f"incident {incident_id} is {incident.state.value}; there is no world left to approve "
            "a change to"
        )
    if incident.state is IncidentState.EXECUTING:
        # ADR-0028 §5: one proposal per incident, executed at most once. The machine has no
        # EXECUTING -> AWAITING_APPROVAL row and the executor refuses a second action; minting a
        # token that could only ever be refused would be an approval the approver did not get.
        raise ApproveError(
            f"incident {incident_id} is executing an action already; one action per incident "
            "(ADR-0028 §5). A second remediation goes through rejection and re-investigation."
        )
    action = catalog.by_id(proposal["action_id"])
    if action is None:
        raise ApproveError(f"action {proposal['action_id']!r} is not in the allowlist catalog")
    target = canonical_service(str(proposal.get("target") or ""))
    if not target:
        raise ApproveError("the proposal names no target")
    token, claims = mint(
        incident_id=incident.id,
        proposal_id=proposal_id,
        action_id=action.id,
        target=target,
        catalog_version=catalog.catalog_version,
        confirm_within_seconds=int(proposal.get("confirm_within_seconds") or 0),
        key=settings.token_key.get_secret_value(),
        ttl_seconds=settings.token_ttl_seconds,
        now=now,
    )
    record = AuditRecord(
        incident_id=incident.id,
        proposal_id=proposal_id,
        action_id=action.id,
        target=target,
        token_id=claims.token_id,
        caller=caller,
        outcome="approved",
        reason=f"expires {claims.expires_at}",
        at=now or datetime.now(UTC),
    )
    audit.append(record)
    # A second approval for an incident already awaiting one is another token, not another
    # transition: several may be minted (the pre-registration's proof mints three) and each is
    # single-use on its own.
    if incident.state is not IncidentState.AWAITING_APPROVAL:
        record_approval_outcome(incident, ApprovalOutcome(kind="approved", audit_id=record.id))
        incidents.save_investigation_state(incident)
    return token, record


def _stores(settings: ExecutorSettings) -> tuple[Any, Any, Any]:
    import psycopg

    from faultline.agents.trajectory import PostgresTrajectoryStore
    from faultline.executor.audit import PostgresAuditStore
    from faultline.orchestrator.store import PostgresIncidentStore

    conn = psycopg.connect(settings.postgres_dsn)
    return PostgresIncidentStore(conn), PostgresTrajectoryStore(conn), PostgresAuditStore(conn)


def run_approve(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="faultline-approve",
        description="Approve one proposed action for one incident: mint its single-use token.",
    )
    p.add_argument("incident_id")
    p.add_argument(
        "--from-run",
        metavar="DIR",
        default=None,
        help="take the proposal from this run directory's *-verdict.json instead of the "
        "incident's own trajectory (the operator path; the pre-registration's repair replay)",
    )
    p.add_argument("--postgres-dsn", default=None)
    args = p.parse_args(argv)

    settings = ExecutorSettings()
    if args.postgres_dsn:
        settings = settings.model_copy(update={"postgres_dsn": args.postgres_dsn})
    from faultline.context.allowlist import load_allowlist

    incidents, trajectories, audit = _stores(settings)
    try:
        if args.from_run:
            proposal, proposal_id = _proposal_from_run(Path(args.from_run))
        else:
            proposal, proposal_id = _proposal_from_trajectory(trajectories, args.incident_id)
        token, record = approve(
            incident_id=args.incident_id,
            incidents=incidents,
            audit=audit,
            settings=settings,
            catalog=load_allowlist(),
            proposal=proposal,
            proposal_id=proposal_id,
            caller=getpass.getuser(),
        )
    except (ApproveError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    print(
        f"approved {record.action_id} -> {record.target} for incident {record.incident_id} "
        f"(proposal {record.proposal_id}); token {record.token_id}, {record.reason}. "
        f"The token follows on stdout, once.",
        file=sys.stderr,
    )
    print(token)
    return 0


def run_execute(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="faultline-execute",
        description="The action plane: execute one approved action, or serve executions.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    one = sub.add_parser("run", help="execute one token and exit")
    one.add_argument("--token", required=True, help="the token faultline-approve printed")
    one.add_argument("--postgres-dsn", default=None)
    serve = sub.add_parser("serve", help="serve POST /execute for T6.3's approval surface")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8100)
    serve.add_argument("--postgres-dsn", default=None)
    args = p.parse_args(argv)

    settings = ExecutorSettings()
    if args.postgres_dsn:
        settings = settings.model_copy(update={"postgres_dsn": args.postgres_dsn})

    if args.command == "run":
        executor = build_executor(settings)
        record = executor.execute(args.token, caller=getpass.getuser())
        print(json.dumps(record.as_dict(), indent=2, sort_keys=True))
        if record.outcome == "executed":
            return 0
        if record.outcome == "error":
            return 1
        return 3

    import uvicorn

    from faultline.executor.app import build_app

    print(
        f"executor serving on {args.host}:{args.port}; kill switch "
        f"{'ON' if settings.kill_switch else 'off'}",
        file=sys.stderr,
    )
    uvicorn.run(build_app(settings), host=args.host, port=args.port)
    return 0


def build_executor(settings: ExecutorSettings) -> Any:
    from faultline.executor.core import Executor, World

    incidents, _trajectories, audit = _stores(settings)
    return Executor(
        key=settings.token_key.get_secret_value(),
        kill_switch=settings.kill_switch,
        incidents=incidents,
        audit=audit,
        world=World(),
    )
