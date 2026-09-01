"""The transition table, and the two stubs that would advance it (T3.5, ADR-0016).

Every transition here is one ADR-0016 names, with the trigger it names. The table is
enforced rather than documented: an illegal transition raises, because a state machine whose
transitions are only a table in a markdown file is a diagram.
"""

from __future__ import annotations

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


INVESTIGABLE = frozenset({IncidentState.TRIAGING})
"""The states an investigation may be started from. **Exactly one, and that is the machine's
answer rather than a choice made here**: `ALLOWED` lets `PLANNING` be entered from `TRIAGING`
and from nowhere else, so `TRIAGING` is the only door into the agent lifecycle.

An incident already past that door - left in `PLANNING` or `INVESTIGATING` by a crashed run -
is deliberately not restartable. `record_investigation_failure` moves such a run to `FAILED`
before it can be stranded, and a `FAILED` incident is terminal by ADR-0016's table. Resuming a
half-finished investigation would need a transition the table does not have, and inventing one
here is the thing this module's docstring exists to prevent."""

INVESTIGATION_PHASES: tuple[tuple[IncidentState, str], ...] = (
    (IncidentState.PLANNING, "planner produced a dispatch plan"),
    (IncidentState.INVESTIGATING, "specialists ran their dispatches"),
    (IncidentState.SYNTHESIZING, "synthesizer produced a verdict"),
)
"""What the runner walks, in order, once an investigation returns.

**It stops at `SYNTHESIZING` and does not enter `PROPOSING`.** `PROPOSING` means a remediation
proposal exists, and the proposer is the one role of the nine that T3.x has not built. An
incident parked in `SYNTHESIZING` says exactly what happened - triage, planning, dispatch and a
verdict - and claims nothing about a proposal. `SYNTHESIZING -> PROPOSING` stays in the table,
unused, for the task that builds it.
"""


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
    verdict = getattr(outcome, "verdict", None)
    for state, trigger in INVESTIGATION_PHASES:
        if state is IncidentState.SYNTHESIZING and verdict is None:
            return
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


def record_approval_outcome(incident: Incident, outcome: object) -> None:
    """Advance `AWAITING_APPROVAL` / `EXECUTING`. **Not built, and unnumbered.**

    The action plane is described in `docs/ARCHITECTURE.md` and load-bearing in
    `docs/THREAT-MODEL.md` - it holds the only write credentials and requires a single-use,
    action-bound approval token - and no task in `docs/PLAN.md` builds it. Recorded there
    under "Discovered omissions".
    """
    raise NotImplementedError(
        "approval and execution outcomes come from the action plane, which has no task "
        "number; see docs/PLAN.md, 'Discovered omissions'"
    )


def is_terminal(state: IncidentState) -> bool:
    return state in TERMINAL
