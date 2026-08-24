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
        {IncidentState.TRIAGING, IncidentState.QUEUED, IncidentState.RESOLVED}
    ),
    IncidentState.QUEUED: frozenset({IncidentState.TRIAGING, IncidentState.RESOLVED}),
    IncidentState.TRIAGING: frozenset(
        {IncidentState.PLANNING, IncidentState.RESOLVED, IncidentState.FAILED}
    ),
    IncidentState.PLANNING: frozenset(
        {IncidentState.INVESTIGATING, IncidentState.RESOLVED, IncidentState.FAILED}
    ),
    IncidentState.INVESTIGATING: frozenset(
        {IncidentState.SYNTHESIZING, IncidentState.RESOLVED, IncidentState.FAILED}
    ),
    IncidentState.SYNTHESIZING: frozenset(
        {IncidentState.PROPOSING, IncidentState.RESOLVED, IncidentState.FAILED}
    ),
    IncidentState.PROPOSING: frozenset(
        {IncidentState.AWAITING_APPROVAL, IncidentState.RESOLVED, IncidentState.FAILED}
    ),
    IncidentState.AWAITING_APPROVAL: frozenset(
        {IncidentState.EXECUTING, IncidentState.RESOLVED, IncidentState.FAILED}
    ),
    IncidentState.EXECUTING: frozenset({IncidentState.RESOLVED, IncidentState.FAILED}),
    IncidentState.RESOLVED: frozenset(
        # Reopening. ADR-0016: a firing episode correlating into a resolved incident inside
        # the settle window puts it back where it was, or in OPEN if it never started.
        {IncidentState.OPEN, IncidentState.QUEUED} | AGENT_DRIVEN | ACTION_PLANE_DRIVEN
    ),
    IncidentState.FAILED: frozenset(),
}
"""`RESOLVED` is terminal in the sense that nothing advances *forward* out of it. It still
accepts a reopen, which is why it is not empty here and `FAILED` is."""


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


def record_agent_outcome(incident: Incident, outcome: object) -> None:
    """Advance an agent-driven state. **Not built: T3.x owns what an outcome is.**

    ADR-0016 names `TRIAGING`, `PLANNING`, `INVESTIGATING`, `SYNTHESIZING` and `PROPOSING`
    with their triggers and deliberately does not design them, because what each agent
    returns - and how a specialist timeout differs from a specialist failure - is T3.x's
    contract. Writing it from this side would be inventing it.
    """
    raise NotImplementedError(
        "agent outcomes arrive at T3.x; ADR-0016 names the states and leaves the contract "
        "to the task that builds the agents"
    )


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
