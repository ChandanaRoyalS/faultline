"""T2.3's property-based tests: the incident machine checked over generated transition sequences.

The plan's row names *"property-based tests on legal and illegal transitions across all eleven
states"*. Until 2026-10-15 the suite had the exhaustive half - BFS reachability over the table
(`test_orchestrator.py`) - and not the generated half: no test drove an incident through arbitrary
sequences of attempted moves and held the machine to the table at every step. These do.

**Generated with a seeded `random.Random`, not Hypothesis.** Adding a dependency re-locks
`uv.lock`, and the lock resolves through the PyTorch CPU index (`[tool.uv.sources]`), which the
environment this was written in could not reach. The properties are the same ones a Hypothesis
strategy would state; the cost is shrinking (a failing sequence is printed whole rather than
minimised), and the seeds make every failure reproducible. Moving to Hypothesis later changes the
generator, not the properties.
"""

from __future__ import annotations

import random

import pytest

from faultline.orchestrator.machine import (
    ALLOWED,
    REJECTABLE,
    TransitionError,
    is_terminal,
    record_rejection,
    transition,
)
from faultline.orchestrator.models import TERMINAL, Incident, IncidentState

STATES = sorted(IncidentState, key=lambda s: s.value)
SEEDS = range(20)
SEQUENCES_PER_SEED = 100
MAX_LENGTH = 30


def reachable_from(start: IncidentState) -> set[IncidentState]:
    seen, frontier = {start}, [start]
    while frontier:
        for nxt in ALLOWED.get(frontier.pop(), frozenset()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return seen


FROM_OPEN = reachable_from(IncidentState.OPEN)


def attempt(incident: Incident, target: IncidentState) -> bool:
    try:
        transition(incident, target, trigger="property test")
    except TransitionError:
        return False
    return True


@pytest.mark.parametrize("seed", SEEDS)
def test_a_move_succeeds_exactly_when_the_table_allows_it(seed: int) -> None:
    """Over random sequences of attempted moves from OPEN, at every step: the move succeeds if and
    only if the target is in the current state's row, a refused move leaves the state unchanged,
    and every state the incident occupies is one the table reaches from OPEN."""
    rng = random.Random(seed)
    for _ in range(SEQUENCES_PER_SEED):
        incident = Incident()
        path = [incident.state]
        for _ in range(rng.randrange(1, MAX_LENGTH)):
            before = incident.state
            target = rng.choice(STATES)
            moved = attempt(incident, target)
            assert moved == (target in ALLOWED[before]), (seed, path, target)
            assert incident.state == (target if moved else before), (seed, path, target)
            assert incident.state in FROM_OPEN, (seed, path)
            path.append(incident.state)


@pytest.mark.parametrize("seed", SEEDS)
def test_the_absolute_terminals_are_never_left(seed: int) -> None:
    """Once FAILED or DUPLICATE_MERGED, no generated move succeeds."""
    rng = random.Random(seed)
    for terminal in (IncidentState.FAILED, IncidentState.DUPLICATE_MERGED):
        incident = Incident(state=terminal)
        for _ in range(MAX_LENGTH):
            assert not attempt(incident, rng.choice(STATES))
            assert incident.state is terminal


@pytest.mark.parametrize("seed", SEEDS)
def test_resolved_only_ever_reopens(seed: int) -> None:
    """From RESOLVED a generated move either is refused or reopens into a non-terminal state -
    never into another end state (ADR-0016: terminal forward-only)."""
    rng = random.Random(seed)
    for _ in range(SEQUENCES_PER_SEED):
        incident = Incident(state=IncidentState.RESOLVED)
        target = rng.choice(STATES)
        if attempt(incident, target):
            assert not is_terminal(incident.state), target
            assert incident.state not in TERMINAL


@pytest.mark.parametrize("seed", SEEDS)
def test_a_rejection_lands_only_from_a_rejectable_state_and_never_without_a_reason(
    seed: int,
) -> None:
    """`record_rejection` from a random state: it moves the incident to REJECTED exactly when the
    state is rejectable and the reason has text; otherwise it raises and the state is unchanged."""
    rng = random.Random(seed)
    reasons = ["", "   ", "\n\t", "wrong service: the culprit is the cache", "x"]
    for _ in range(SEQUENCES_PER_SEED):
        start = rng.choice(STATES)
        reason = rng.choice(reasons)
        incident = Incident(state=start)
        should_land = start in REJECTABLE and bool(reason.strip())
        try:
            record_rejection(incident, reason)
            landed = True
        except (TransitionError, ValueError):
            landed = False
        assert landed == should_land, (start, reason)
        assert incident.state == (IncidentState.REJECTED if landed else start), (start, reason)


def test_every_ordered_pair_of_states_is_decided_by_the_table() -> None:
    """The exhaustive companion to the generated sequences: all 14 x 14 ordered pairs, each
    attempted on a fresh incident, succeed exactly when the table has them."""
    for source in STATES:
        for target in STATES:
            incident = Incident(state=source)
            assert attempt(incident, target) == (target in ALLOWED[source]), (source, target)
