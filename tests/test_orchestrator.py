"""T2.2 against the eight events T2.1 actually published. No Redis, no Postgres.

The fixtures are `docs/evidence/t2.1-live-smoke/stream-events.txt` - the real `XRANGE` dump
from the run where the receiver consumed a live `cart-redis-misconfig` injection end to end.
Replaying them in order is the measured case ADR-0016 was designed against, and the thing
worth pinning: one incident, four episodes, `emailservice` joining rather than opening, and
`RESOLVED` at the last resolution.

The seams - `IncidentStore`, `CorrelationPolicy`, `EventSource` - are substituted, so the
logic runs and the durability does not. Same split as ingest: the rule is logic and belongs
here, the durability is Postgres's and is asserted in ADR-0016 rather than mocked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import redis

from faultline.ingest.models import AlertEvent, AlertStatus
from faultline.orchestrator.cap import InvestigationCap
from faultline.orchestrator.consumer import (
    ConsumerLoop,
    RedisEventSource,
    ReplayEventSource,
    SocketTimeoutError,
    configured_socket_timeout,
    socket_timeout_for,
)
from faultline.orchestrator.core import Orchestrator
from faultline.orchestrator.correlation import TimeOverlapPolicy
from faultline.orchestrator.machine import ALLOWED, TransitionError, transition
from faultline.orchestrator.models import (
    TERMINAL,
    Episode,
    Incident,
    IncidentState,
    JoinRule,
    Severity,
)
from faultline.orchestrator.settings import OrchestratorSettings
from faultline.orchestrator.store import InMemoryIncidentStore

DUMP = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "evidence"
    / "t2.1-live-smoke"
    / "stream-events.txt"
)

SETTLE = timedelta(minutes=5)


def captured_events() -> list[AlertEvent]:
    """The eight published events, in stream order.

    `XRANGE` prints three lines per entry: the stream id, the field name `event`, the JSON.
    """
    lines = DUMP.read_text().splitlines()
    return [AlertEvent.model_validate_json(lines[i]) for i in range(2, len(lines), 3)]


def orchestrator(max_concurrent: int = 3) -> tuple[Orchestrator, InMemoryIncidentStore]:
    store = InMemoryIncidentStore()
    return (
        Orchestrator(
            store=store,
            policy=TimeOverlapPolicy(SETTLE),
            cap=InvestigationCap(max_concurrent),
            settle_window=SETTLE,
        ),
        store,
    )


def test_the_dump_is_the_one_the_evidence_describes() -> None:
    """Guard the fixture. If the capture is replaced, these tests are about something else."""
    events = captured_events()

    assert len(events) == 8
    assert [e.status.value for e in events] == [
        "firing",
        "firing",
        "firing",
        "resolved",
        "firing",
        "resolved",
        "resolved",
        "resolved",
    ]
    assert {e.service for e in events} == {
        "checkoutservice",
        "frontend",
        "loadgenerator",
        "emailservice",
    }


# --- the measured case --------------------------------------------------------


def test_the_eight_events_produce_one_incident_with_four_episodes() -> None:
    """One fault, four alerts, one incident.

    This is the alert-storm-to-one-incident case `docs/evidence/gate-1/README.md:19` named.
    Without correlation this system opens four incidents for one fault and investigates the
    same root cause four times.
    """
    ingest, store = orchestrator()

    results = [ingest.apply(e) for e in captured_events()]

    assert len(store.incidents) == 1, "four alerts, one fault, one incident"
    incident = next(iter(store.incidents.values()))
    assert len(incident.episodes) == 4
    assert sum(1 for r in results if r.opened) == 1
    assert sum(1 for r in results if r.joined) == 3


def test_the_post_revert_emailservice_alert_joins_rather_than_opening() -> None:
    """The hard case, and the one ADR-0016 exists to answer.

    `emailservice` fires ~2m30s after the revert - recovery traffic failing, with `for: 2m` -
    and arrives 15 seconds after `checkoutservice` has already resolved. An orchestrator that
    treated it as a new incident would be investigating the first incident's recovery as
    though it were a second fault.
    """
    ingest, store = orchestrator()
    events = captured_events()

    results = [ingest.apply(e) for e in events]

    email_firing = next(
        i
        for i, e in enumerate(events)
        if e.service == "emailservice" and e.status.value == "firing"
    )
    assert results[email_firing].joined, "joined the open cart incident"
    assert not results[email_firing].opened
    assert len(store.incidents) == 1

    incident = next(iter(store.incidents.values()))
    assert "emailservice" in {e.service for e in incident.episodes.values()}


def test_the_incident_resolves_at_the_last_resolution() -> None:
    """Every episode resolved closes it, from whatever state it was in.

    It closes from `TRIAGING` here: the cap had room, so it was admitted on open, and T3.x
    does not exist to advance it further. That is the ADR's point about the alerts-resolving
    transition - it comes from any non-terminal state, and it does not cancel the
    investigation, because the fault being over does not answer what caused it.
    """
    ingest, store = orchestrator()
    events = captured_events()

    for event in events[:-1]:
        ingest.apply(event)
    incident = next(iter(store.incidents.values()))
    assert incident.state is IncidentState.TRIAGING, "still investigating while one alert holds"

    last = ingest.apply(events[-1])

    assert last.resolved_incident
    assert incident.state is IncidentState.RESOLVED
    assert incident.resolution == "alerts_resolved"
    assert incident.state_before_resolution is IncidentState.TRIAGING, "remembered, for a reopen"
    assert incident.resolved_at == events[-1].received_at


def test_every_episode_is_attached_with_the_alert_it_came_from() -> None:
    """What T4.1 has to be able to ask: which incident got which alerts, and when."""
    ingest, store = orchestrator()
    for event in captured_events():
        ingest.apply(event)

    incident = next(iter(store.incidents.values()))
    by_service = {e.service: e for e in incident.episodes.values()}

    assert set(by_service) == {"checkoutservice", "frontend", "loadgenerator", "emailservice"}
    assert all(e.is_resolved for e in by_service.values())
    assert all(e.alertname == "ServiceHighErrorRate" for e in by_service.values())
    assert by_service["emailservice"].starts_at == datetime(
        2026, 8, 24, 11, 15, 45, 583000, tzinfo=UTC
    )
    assert incident.severity is Severity.CRITICAL, "every rule in this incident is critical"


def test_replaying_the_whole_stream_changes_nothing() -> None:
    """Stream redelivery, which is not the same mechanism as ingest's dedupe.

    Ingest suppresses Alertmanager repeats and retries (ADR-0015). This suppresses an event
    published exactly once and delivered more than once - which is what happens after a crash
    between the state write and the ack, and that ordering is deliberate.
    """
    ingest, store = orchestrator()
    events = captured_events()
    for event in events:
        ingest.apply(event)
    incident = next(iter(store.incidents.values()))
    before = (incident.state, len(incident.episodes), incident.resolved_at)

    again = [ingest.apply(e) for e in events]

    assert all(r.duplicate for r in again)
    assert len(store.incidents) == 1
    assert (incident.state, len(incident.episodes), incident.resolved_at) == before


def test_the_loop_acks_every_entry_it_applies() -> None:
    """The captured events through the real consumer loop, not just through `apply`."""
    ingest, store = orchestrator()
    source = ReplayEventSource(captured_events())

    results = ConsumerLoop(source=source, orchestrator=ingest, batch=32).run_once()

    assert len(results) == 8
    assert len(source.acked) == 8, "one ack per entry, after its state change"
    assert len(store.incidents) == 1


# --- correlation ---------------------------------------------------------------


def test_correlation_never_matches_on_fingerprint_alone() -> None:
    """Measured: the same four fingerprints appeared in two incidents forty minutes apart.

    The fingerprint is a pure function of the alert's labels, so matching on it would merge an
    incident with every previous incident on the same service. Here the first incident is long
    closed - well outside the settle window - and the identical fingerprints must not pull the
    second into it.
    """
    ingest, store = orchestrator()
    events = captured_events()
    for event in events:
        ingest.apply(event)

    later = _shifted(events[0], timedelta(hours=1))
    result = ingest.apply(later)

    assert result.opened, "a new incident, an hour later, despite the identical fingerprint"
    assert len(store.incidents) == 2


def test_a_firing_inside_the_settle_window_reopens_rather_than_opening() -> None:
    """The recovery alert arriving after the last resolution - timing, not kind.

    In both captures `emailservice` fired while other alerts were still firing, so it joined
    the open incident. This is the same event arriving a little later, which the captures do
    not contain and the settle window exists for.
    """
    ingest, store = orchestrator()
    events = captured_events()
    for event in events:
        ingest.apply(event)
    incident = next(iter(store.incidents.values()))
    assert incident.state is IncidentState.RESOLVED

    late = _shifted(events[4], timedelta(minutes=2))  # emailservice firing, 2 min later
    result = ingest.apply(late)

    assert result.joined and not result.opened
    assert len(store.incidents) == 1
    assert incident.state is IncidentState.TRIAGING, "back to where it was before it closed"
    assert incident.resolved_at is None and incident.resolution is None


def test_a_firing_outside_the_settle_window_opens_a_new_incident() -> None:
    ingest, store = orchestrator()
    events = captured_events()
    for event in events:
        ingest.apply(event)

    much_later = _shifted(events[4], timedelta(minutes=30))
    result = ingest.apply(much_later)

    assert result.opened
    assert len(store.incidents) == 2


def test_a_resolved_for_an_episode_no_incident_holds_is_ignored() -> None:
    """ADR-0015 publishes these deliberately - a receiver down for the firing, or restarted.

    Inventing an incident to close is worse than dropping a close for one that never opened
    here, so it is recorded as ignored rather than acted on.
    """
    ingest, store = orchestrator()

    result = ingest.apply(captured_events()[3])  # checkoutservice resolved, nothing opened

    assert result.ignored_reason is not None
    assert store.incidents == {}


# --- the cap -------------------------------------------------------------------
#
# Every test here substitutes the correlation policy, and that is not a convenience.
# `TimeOverlapPolicy` joins a firing episode to any live incident, so at most one incident
# is ever non-terminal and **the cap is unreachable through it** - see the note in
# `faultline.orchestrator.cap`. The cap becomes reachable when T2.4's `DependencyPolicy` can
# decline to correlate. `_AlwaysNew` is that shape, a policy that always declines.


class _AlwaysNew:
    """A correlation policy that never joins. The shape T2.4's will have when it declines."""

    last_rule = JoinRule.NO_CANDIDATE
    """Every decline opens an incident, and T4.1 records that as a decision like any other."""

    def match(self, event: AlertEvent, candidates: list[Incident]) -> Incident | None:
        return None


def uncorrelated(max_concurrent: int) -> tuple[Orchestrator, InMemoryIncidentStore]:
    store = InMemoryIncidentStore()
    return (
        Orchestrator(
            store=store,
            policy=_AlwaysNew(),
            cap=InvestigationCap(max_concurrent),
            settle_window=SETTLE,
        ),
        store,
    )


def test_an_incident_opened_under_a_full_cap_is_queued() -> None:
    ingest, store = uncorrelated(max_concurrent=1)
    events = captured_events()

    ingest.apply(events[0])
    ingest.apply(events[1])

    states = sorted(i.state.value for i in store.incidents.values())
    assert states == ["queued", "triaging"], "the cap held; the second waits"
    assert store.active_count() == 1


def test_a_freed_slot_admits_the_highest_severity_then_oldest() -> None:
    """Strict priority, FIFO within a severity.

    Note what this test needs in order to exist: a `warning`. The catalog's scenarios alert
    almost entirely `ServiceHighErrorRate` and one `ServiceNoTraffic`, both `critical`, so the
    ordering has nothing to sort in any scored run - it is FIFO with extra steps there. The
    warning here is constructed by changing one label.
    """
    ingest, store = uncorrelated(max_concurrent=1)
    events = captured_events()
    ingest.apply(events[0])
    holder = next(iter(store.incidents.values()))

    warning = _shifted(events[1], timedelta(minutes=1))
    warning.alert["labels"]["severity"] = "warning"
    ingest.apply(warning)
    ingest.apply(_shifted(events[2], timedelta(minutes=2)))

    assert len(store.queued()) == 2
    assert [i.severity for i in store.queued()] == [Severity.WARNING, Severity.CRITICAL]

    ingest.apply(_resolution_of(events[0], holder_received=holder.last_activity_at))

    admitted = [i for i in store.incidents.values() if i.state is IncidentState.TRIAGING]
    assert len(admitted) == 1
    assert admitted[0].severity is Severity.CRITICAL, "the critical one jumped the warning"


def test_the_queue_orders_by_severity_then_age() -> None:
    """The ordering itself, without a store or an event in sight."""
    older_warning = Incident(opened_at=datetime(2026, 8, 24, 10, tzinfo=UTC))
    older_warning.episodes["w"] = _episode(Severity.WARNING)
    newer_critical = Incident(opened_at=datetime(2026, 8, 24, 11, tzinfo=UTC))
    newer_critical.episodes["c"] = _episode(Severity.CRITICAL)
    oldest_critical = Incident(opened_at=datetime(2026, 8, 24, 9, tzinfo=UTC))
    oldest_critical.episodes["c"] = _episode(Severity.CRITICAL)

    chosen = InvestigationCap.next_admission([older_warning, newer_critical, oldest_critical])

    assert chosen is oldest_critical, "severity first, then oldest within it"
    assert InvestigationCap.next_admission([]) is None


def test_a_queued_incident_that_resolves_before_starting_says_so() -> None:
    """ADR-0016 marks this for decision and chose to abandon. The condition was that it be
    recorded rather than silent, and T4.1 must assert its incident was actually investigated.
    """
    ingest, store = uncorrelated(max_concurrent=1)
    events = captured_events()
    ingest.apply(events[0])
    ingest.apply(events[1])
    queued = next(i for i in store.incidents.values() if i.state is IncidentState.QUEUED)

    ingest.apply(_resolution_of(events[1], holder_received=queued.last_activity_at))

    assert queued.state is IncidentState.RESOLVED
    assert queued.resolution == "never_started", "visible as a dropped incident, not as noise"


# --- the socket must outlive the block ------------------------------------------
#
# The one failure the eight-event replay could not have found. A blocking XREADGROUP that
# returns *nothing* is the only thing that waits long enough to hit the socket timeout, and
# no fixture-driven test produces an empty stream - a replay source always has an event to
# hand back. So the invariant is asserted at construction, where it needs no stream at all.


def source_with(client: redis.Redis, block_ms: int) -> RedisEventSource:
    return RedisEventSource(
        client,
        stream="faultline:alerts",
        group="orchestrator",
        consumer="orchestrator-1",
        idle_ms=60_000,
        dead_letter_stream="faultline:alerts:dead",
        block_ms=block_ms,
    )


def test_connect_sizes_the_socket_to_outlive_its_own_blocking_read() -> None:
    """The relationship, on the constructor the CLI actually uses."""
    source = RedisEventSource.connect(
        "redis://localhost:6379/0",
        stream="faultline:alerts",
        group="orchestrator",
        consumer="orchestrator-1",
        idle_ms=60_000,
        dead_letter_stream="faultline:alerts:dead",
        block_ms=5000,
    )

    timeout = configured_socket_timeout(source.client)

    assert timeout is not None
    assert timeout > source.block_ms / 1000.0, "the socket must not give up first"
    assert timeout == socket_timeout_for(5000)


def test_the_default_client_against_the_default_block_is_refused() -> None:
    """The exact crash, pinned. redis-py 8.1.0 defaults socket_timeout to 5s and this
    module's block_ms defaults to 5000 - the same instant, so the race was certain rather
    than close. It reached production because a non-empty read returns immediately."""
    default_client = redis.from_url("redis://localhost:6379/0")

    with pytest.raises(SocketTimeoutError, match="gives up before the server answers"):
        source_with(default_client, block_ms=OrchestratorSettings().block_ms)


def test_the_shipped_settings_satisfy_the_invariant() -> None:
    """Changing either number alone breaks this.

    `block_ms` and the socket timeout are derived from one value now, but a future edit that
    reintroduces a second source for either has to pass through here.
    """
    settings = OrchestratorSettings()

    timeout = socket_timeout_for(settings.block_ms)

    assert timeout > settings.block_ms / 1000.0
    source_with(redis.from_url("redis://x", socket_timeout=timeout), settings.block_ms)


def test_an_unbounded_socket_timeout_is_allowed_deliberately() -> None:
    """`None` means wait forever, which cannot lose this race. Documented, not accidental -
    the cost is that a dropped connection is noticed late rather than at the timeout."""
    source_with(redis.from_url("redis://x", socket_timeout=None), block_ms=5000)


# --- the machine ---------------------------------------------------------------


def test_the_transition_table_refuses_what_adr_0016_does_not_list() -> None:
    """The table is enforced, not documented. A machine whose transitions live only in a
    markdown table is a diagram."""
    incident = Incident(state=IncidentState.OPEN)

    with pytest.raises(TransitionError, match="not a transition"):
        transition(incident, IncidentState.EXECUTING, trigger="a test")


def test_the_state_that_still_needs_an_unbuilt_component_is_a_stub_that_says_so() -> None:
    """One of the two stubs is still a stub, and its message should name what is missing.

    `record_agent_outcome` stopped being one at T3.5 - the runner is the component it was
    waiting for. The action plane still has no task number, so approval and execution outcomes
    have nothing to arrive from.
    """
    from faultline.orchestrator import machine

    incident = Incident(state=IncidentState.TRIAGING)
    with pytest.raises(NotImplementedError, match="no task number"):
        machine.record_approval_outcome(incident, object())


# --- helpers -------------------------------------------------------------------


def _shifted(event: AlertEvent, by: timedelta) -> AlertEvent:
    """The same alert, one episode later. Constructed, and marked as such where used."""
    moved = event.model_copy(deep=True)
    moved.received_at = event.received_at + by
    moved.starts_at = event.starts_at + by
    moved.episode_key = f"{event.fingerprint}@{moved.starts_at.isoformat()}"
    moved.alert["startsAt"] = moved.starts_at.isoformat()
    return moved


def _episode(severity: Severity) -> Episode:
    moment = datetime(2026, 8, 24, 11, tzinfo=UTC)
    return Episode(
        episode_key="k",
        fingerprint="f",
        service="s",
        severity=severity,
        alertname="ServiceHighErrorRate",
        starts_at=moment,
        attached_at=moment,
    )


def _resolution_of(firing: AlertEvent, holder_received: datetime | None) -> AlertEvent:
    """The resolved half of a constructed firing."""
    resolved = firing.model_copy(deep=True)
    resolved.status = AlertStatus.RESOLVED
    resolved.received_at = (holder_received or firing.received_at) + timedelta(minutes=1)
    resolved.ends_at = resolved.received_at
    return resolved


# --- T2.3: the state graph, checked against the specification --------------------
#
# docs/spec/project-proposal-rev8.pdf p.5 names the states. ADR-0016 took its count
# from docs/ARCHITECTURE.md instead. Both say eleven, so the count never disagreed --
# which is why the *set* was never compared. These tests compare the set.

PLAN_STATES: dict[str, IncidentState | None] = {
    "DETECTED": IncidentState.OPEN,
    "TRIAGED": IncidentState.TRIAGING,
    "INVESTIGATING": IncidentState.INVESTIGATING,
    "HYPOTHESIS": IncidentState.SYNTHESIZING,
    "AWAITING_APPROVAL": IncidentState.AWAITING_APPROVAL,
    "REMEDIATING": IncidentState.EXECUTING,
    "RESOLVED": IncidentState.RESOLVED,
    "FAILED": IncidentState.FAILED,
    "DUPLICATE_MERGED": None,
    "BUDGET_EXHAUSTED": None,
    "REJECTED": None,
}

# Failure-scenario table, project-proposal-rev8.pdf pp.10-11. Only the rows whose
# Mitigation or Recovery column names a state-level outcome appear here.
FAILURE_ROWS_NAMING_AN_ABSENT_STATE: dict[str, str] = {
    "Alert storm: cascading failure fires 200 alerts at once": "DUPLICATE_MERGED",
    "Wrong root cause confidently reported": "REJECTED",
    "Runaway cost: investigation loops, burns $40 on one incident": "BUDGET_EXHAUSTED",
}


def _reachable_from(start: IncidentState) -> set[IncidentState]:
    seen = {start}
    frontier = [start]
    while frontier:
        current = frontier.pop()
        for nxt in ALLOWED.get(current, frozenset()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return seen


def test_every_state_is_reachable_from_open() -> None:
    """Gate 2's own criterion. A state nothing can reach is decoration."""
    unreachable = set(IncidentState) - _reachable_from(IncidentState.OPEN)
    assert not unreachable, f"unreachable from OPEN: {sorted(s.value for s in unreachable)}"


def test_failed_is_absolutely_terminal() -> None:
    assert ALLOWED[IncidentState.FAILED] == frozenset()


def test_resolved_reopens_backward_and_never_advances() -> None:
    """`RESOLVED` is terminal forward-only.

    ADR-0016 lets a reopen put a settled incident back into the lifecycle, which is why
    its successor set is not empty. What it must never do is step into *another* end
    state -- a resolved incident cannot become a failed one without being reopened first.
    """
    successors = ALLOWED[IncidentState.RESOLVED]
    assert successors, "RESOLVED must accept a reopen"
    assert not (successors & TERMINAL), f"RESOLVED reaches an end state: {successors & TERMINAL}"


def test_the_matching_count_is_a_coincidence() -> None:
    """Eleven and eleven -- and three of the plan's states are not here at all.

    This test exists so the coincidence can never again read as agreement.
    """
    assert len(PLAN_STATES) == len(IncidentState) == 11
    absent = {name for name, mapped in PLAN_STATES.items() if mapped is None}
    assert absent == {"DUPLICATE_MERGED", "BUDGET_EXHAUSTED", "REJECTED"}
    added = set(IncidentState) - {m for m in PLAN_STATES.values() if m is not None}
    assert added == {IncidentState.QUEUED, IncidentState.PLANNING, IncidentState.PROPOSING}


def test_every_absent_plan_state_is_named_by_a_failure_row() -> None:
    """Each absence costs a row of the failure table -- ADR-0016's addendum says which."""
    assert set(FAILURE_ROWS_NAMING_AN_ABSENT_STATE.values()) == {
        name for name, mapped in PLAN_STATES.items() if mapped is None
    }


def test_mapped_plan_states_all_exist() -> None:
    for name, mapped in PLAN_STATES.items():
        if mapped is not None:
            assert mapped in set(IncidentState), f"{name} maps to a state that vanished"
