"""The transition table, and the two stubs that would advance it (T3.5, ADR-0016).

Every transition here is one ADR-0016 names, with the trigger it names. The table is
enforced rather than documented: an illegal transition raises, because a state machine whose
transitions are only a table in a markdown file is a diagram.
"""

from __future__ import annotations

from dataclasses import dataclass

from faultline.orchestrator.models import (
    ACTION_PLANE_DRIVEN,
    AGENT_DRIVEN,
    TERMINAL,
    Incident,
    IncidentState,
)

ALLOWED: dict[IncidentState, frozenset[IncidentState]] = {
    IncidentState.OPEN: frozenset(
        {
            IncidentState.TRIAGING,
            IncidentState.QUEUED,
            IncidentState.RESOLVED,
            IncidentState.DUPLICATE_MERGED,
        }
    ),
    IncidentState.QUEUED: frozenset(
        {
            IncidentState.TRIAGING,
            IncidentState.RESOLVED,
            IncidentState.DUPLICATE_MERGED,
        }
    ),
    IncidentState.TRIAGING: frozenset(
        {
            IncidentState.PLANNING,
            # T6.2, ADR-0016 Addendum 4: the operator path. A human approves an action for an
            # incident no agent has investigated, and it goes through the executor rather than
            # around it. From TRIAGING only - the one state in which no investigation is running
            # that could later try to move the incident somewhere else.
            IncidentState.AWAITING_APPROVAL,
            IncidentState.RESOLVED,
            IncidentState.FAILED,
            IncidentState.BUDGET_EXHAUSTED,
            IncidentState.DUPLICATE_MERGED,
        }
    ),
    IncidentState.PLANNING: frozenset(
        {
            IncidentState.INVESTIGATING,
            IncidentState.RESOLVED,
            IncidentState.FAILED,
            IncidentState.BUDGET_EXHAUSTED,
            IncidentState.DUPLICATE_MERGED,
        }
    ),
    IncidentState.INVESTIGATING: frozenset(
        {
            IncidentState.SYNTHESIZING,
            IncidentState.RESOLVED,
            IncidentState.FAILED,
            IncidentState.BUDGET_EXHAUSTED,
            IncidentState.DUPLICATE_MERGED,
        }
    ),
    IncidentState.SYNTHESIZING: frozenset(
        {
            IncidentState.PROPOSING,
            IncidentState.RESOLVED,
            IncidentState.FAILED,
            IncidentState.REJECTED,
            IncidentState.BUDGET_EXHAUSTED,
            IncidentState.DUPLICATE_MERGED,
        }
    ),
    IncidentState.PROPOSING: frozenset(
        {
            IncidentState.AWAITING_APPROVAL,
            IncidentState.RESOLVED,
            IncidentState.FAILED,
            IncidentState.REJECTED,
            IncidentState.BUDGET_EXHAUSTED,
            IncidentState.DUPLICATE_MERGED,
        }
    ),
    IncidentState.AWAITING_APPROVAL: frozenset(
        {
            IncidentState.EXECUTING,
            IncidentState.RESOLVED,
            IncidentState.FAILED,
            IncidentState.REJECTED,
        }
    ),
    IncidentState.EXECUTING: frozenset({IncidentState.RESOLVED, IncidentState.FAILED}),
    IncidentState.REJECTED: frozenset(
        # T2.3: "exits to targeted re-investigation, reason required". `PLANNING` is that
        # exit - re-planning with the rejection as an input is what "targeted" means. The
        # reason lives on the incident; `record_rejection` will not move one without it.
        {IncidentState.PLANNING, IncidentState.RESOLVED, IncidentState.FAILED}
    ),
    IncidentState.BUDGET_EXHAUSTED: frozenset(
        # T2.3: "re-enterable when the cap is raised". It resumes at `PLANNING` and not
        # mid-dispatch, because the plan it was executing was costed against the old cap.
        {IncidentState.PLANNING, IncidentState.RESOLVED, IncidentState.FAILED}
    ),
    IncidentState.RESOLVED: frozenset(
        # Reopening. ADR-0016: a firing episode correlating into a resolved incident inside
        # the settle window puts it back where it was, or in OPEN if it never started.
        {IncidentState.OPEN, IncidentState.QUEUED} | AGENT_DRIVEN | ACTION_PLANE_DRIVEN
    ),
    IncidentState.FAILED: frozenset(),
    IncidentState.DUPLICATE_MERGED: frozenset(),
}
"""`RESOLVED` is terminal in the sense that nothing advances *forward* out of it. It still
accepts a reopen, which is why it is not empty here and `FAILED` and `DUPLICATE_MERGED`
are."""


class TransitionError(RuntimeError):
    """An attempted transition the machine does not allow."""


def transition(incident: Incident, to: IncidentState, *, trigger: str) -> None:
    """Move `incident` to `to`, or raise. `trigger` is what caused it, for the message.

    Deliberately not silent on a no-op: re-entering the state you are in usually means two
    code paths both think they own the transition, which is worth finding.
    """
    if to not in ALLOWED[incident.state]:
        raise TransitionError(
            f"incident {incident.id}: {incident.state.value} -> {to.value} is not a "
            f"transition this machine has (trigger: {trigger}). "
            "The table is ADR-0016's; add it there before adding it here."
        )
    incident.state = to


INVESTIGABLE = frozenset({IncidentState.TRIAGING, IncidentState.REJECTED})
"""The states an investigation may be started from. **Two, and both are the machine's answer
rather than a choice made here**: `ALLOWED` lets `PLANNING` be entered from `TRIAGING` and from
`REJECTED`, and from nowhere else, so those are the two doors into the agent lifecycle.

`REJECTED` is T6.3's, and it was in the table from Phase 2 with nothing able to walk it: T2.3
wrote *"exits to targeted re-investigation, reason required"*, and until the rejection ledger
existed there was no reason to require. The re-entry starts at `PLANNING` like any other
investigation - `phases_for` walks the same four phases - and it reuses the triage it already
has, because triage is a pure function of the episodes, the catalog and the radius and paying a
model to recompute it would be paying for a known answer.

An incident already past that door - left in `PLANNING` or `INVESTIGATING` by a crashed run -
is deliberately not restartable. `record_investigation_failure` moves such a run to `FAILED`
before it can be stranded, and a `FAILED` incident is terminal by ADR-0016's table. Resuming a
half-finished investigation would need a transition the table does not have, and inventing one
here is the thing this module's docstring exists to prevent."""

INVESTIGATION_PHASES: tuple[tuple[IncidentState, str], ...] = (
    (IncidentState.PLANNING, "planner produced a dispatch plan"),
    (IncidentState.INVESTIGATING, "specialists ran their dispatches"),
    (IncidentState.SYNTHESIZING, "synthesizer produced a verdict"),
    (IncidentState.PROPOSING, "proposer produced a remediation proposal"),
)
"""What the runner walks, in order, once an investigation returns.

**`PROPOSING` is entered only when a proposal exists** - built at T3.9, and until then this
tuple stopped at `SYNTHESIZING` because the proposer was the one role of the nine that had no
implementation. It still stops there whenever the proposer did not run, was refused twice, or
had no verdict to work from: an incident parked in `SYNTHESIZING` says exactly what happened and
claims nothing about a proposal.

**An abstention advances the state.** `remediation_class: "none"` is a proposal - the proposer
ran, read the evidence and declined - and ADR-0022 §1.2 is explicit that an abstention is
neither right nor wrong rather than absent. `PROPOSING` means *a proposal exists*, not *an
action was proposed*, and the incident's next state is the action plane's to decide.
"""


def phases_for(outcome: object) -> tuple[tuple[IncidentState, str], ...]:
    """The phases a finished investigation **evidences**, in order, and no further.

    One function because there are two walkers - `record_agent_outcome` here, and
    `agents.runner.run_investigation`, which walks the same phases itself so it can persist the
    incident after each one. T3.9 found them disagreeing: the proposer's state was added here
    and the runner advanced to `PROPOSING` on every run, proposer or not. A rule with two
    implementations has two behaviours, so the rule is here and both walk what it returns.

    Typed as `object` for the same reason `record_agent_outcome` is: `faultline.agents` imports
    `faultline.orchestrator` and not the other way round.
    """
    verdict = getattr(outcome, "verdict", None)
    proposal = getattr(outcome, "proposal", None)
    reached: list[tuple[IncidentState, str]] = []
    for state, trigger in INVESTIGATION_PHASES:
        if state is IncidentState.SYNTHESIZING and verdict is None:
            break
        if state is IncidentState.PROPOSING and proposal is None:
            break
        reached.append((state, trigger))
    return tuple(reached)


def record_agent_outcome(incident: Incident, outcome: object) -> None:
    """Advance an agent-driven state from a finished investigation. **Built at T3.5.**

    ADR-0016 named `TRIAGING`, `PLANNING`, `INVESTIGATING`, `SYNTHESIZING` and `PROPOSING` with
    their triggers and deliberately left the contract to T3.x, because what an agent returns -
    and how a specialist timeout differs from a specialist failure - was not decided yet. It is
    now: `outcome` is an `InvestigationResult`, and this walks the phases it evidences.

    Typed as `object` because `faultline.agents` imports `faultline.orchestrator` and not the
    other way round; the duck-typing is deliberate and the attributes read here are the ones
    ADR-0020 §5 fixed.

    A result carrying no verdict does **not** advance to `SYNTHESIZING`. There is nothing to
    score and nothing to propose from, and marking it as synthesized would put a state on the
    incident that its own trajectory contradicts.
    """
    for state, trigger in phases_for(outcome):
        transition(incident, state, trigger=trigger)


def record_investigation_failure(incident: Incident, reason: str) -> None:
    """An investigation that raised. **`FAILED`, from wherever it got to.**

    ADR-0020 §5 draws the line: budget exhaustion produces a *flagged verdict* and never a
    `FAILED` incident, because a partial diagnosis is scoreable. This is the other case - the
    run did not finish at all - and leaving the incident in `PLANNING` or `INVESTIGATING` would
    strand it in a state nothing can advance and `INVESTIGABLE` will not accept.
    """
    if incident.state in TERMINAL:
        return
    transition(incident, IncidentState.FAILED, trigger=f"investigation failed: {reason}")


@dataclass(frozen=True, slots=True)
class ApprovalOutcome:
    """What the action plane reports (T6.2). `kind` is one of four:

    - `approved` - a token was minted for a proposal; the incident waits for execution;
    - `executed` - the executor performed the action; the incident is `EXECUTING` until the
      world's alerts resolve it (the orchestrator's ordinary path) or the operator fails it;
    - `refused` - the executor did not act; the incident does not move, and the audit says why;
    - `failed` - the command ran and did not succeed; the incident is `FAILED`, with the audit
      row named, because a half-applied change is not a state a machine should call anything else.

    `audit_id` is the `action_audit` row, so every transition this causes points at its evidence.
    """

    kind: str
    audit_id: str | None = None


def record_approval_outcome(incident: Incident, outcome: ApprovalOutcome) -> None:
    """Advance `AWAITING_APPROVAL` / `EXECUTING` from what the action plane reports (T6.2).

    Built at T6.2 against ADR-0016's table, with one row added there first (Addendum 4):
    `TRIAGING -> AWAITING_APPROVAL`, the operator path - an approval given before any agent has
    run, so that a manual remediation goes through the same executor, token and audit as an
    agent-proposed one, rather than around them. T6.3's approve / reject surface will call the
    same function; the CLI `faultline-approve` calls it today.
    """
    if outcome.kind == "approved":
        transition(
            incident,
            IncidentState.AWAITING_APPROVAL,
            trigger=f"approval minted (audit {outcome.audit_id or 'n/a'})",
        )
    elif outcome.kind == "executed":
        transition(
            incident, IncidentState.EXECUTING, trigger=f"action executed (audit {outcome.audit_id})"
        )
    elif outcome.kind == "failed":
        transition(
            incident, IncidentState.FAILED, trigger=f"action failed (audit {outcome.audit_id})"
        )
    elif outcome.kind == "refused":
        return
    else:
        raise ValueError(f"unknown approval outcome kind {outcome.kind!r}")


REJECTABLE = frozenset(
    {IncidentState.PROPOSING, IncidentState.SYNTHESIZING, IncidentState.AWAITING_APPROVAL}
)
"""Where a rejection can arrive from, read out of `ALLOWED` rather than written twice: the three
states with `REJECTED` in their row. A rejection of an incident that has not proposed anything, or
that is already executing, is a mistake the surface should name rather than a transition."""


def record_rejection(incident: Incident, reason: str) -> str:
    """A human rejected the proposal. **The reason is required and this is where that is true.**

    T2.3's sentence - *"`REJECTED` exits to targeted re-investigation, reason required"* - has
    been in `ALLOWED`'s comment since Phase 2 as a promise about a function that did not exist.
    This is it. The reason is cleaned by `rejections.clean_reason`, which raises on whitespace,
    so an incident cannot reach `REJECTED` without something to re-investigate *with*; the
    cleaned text is returned for the caller to store, because the machine records states and the
    ledger records evidence.

    The incident does not move from anywhere else. A rejection arriving for an `EXECUTING`
    incident is refused here rather than at the route, for the same reason one action per
    incident moved into the executor (ADR-0038 Addendum 2): a rule enforced only by whichever
    layer happens to be asked is a rule about that layer.
    """
    from faultline.orchestrator.rejections import clean_reason

    cleaned = clean_reason(reason)
    if incident.state not in REJECTABLE:
        legal = ", ".join(sorted(s.value for s in REJECTABLE))
        raise TransitionError(
            f"incident {incident.id} is in state {incident.state.value}; a proposal can be "
            f"rejected from {legal} only. "
            "See ADR-0016 and faultline.orchestrator.machine.REJECTABLE."
        )
    transition(
        incident, IncidentState.REJECTED, trigger=f"operator rejected the proposal: {cleaned}"
    )
    return cleaned


def is_terminal(state: IncidentState) -> bool:
    return state in TERMINAL
