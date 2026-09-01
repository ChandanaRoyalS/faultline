"""T2.3's integration tests: `PostgresIncidentStore`, against a real Postgres.

The class's own docstring reads *"The real one. Not exercised by `make check`"* - and that was
true of every test in this repository. The suite used the in-memory double exclusively, so
this SQL had never run anywhere except a live smoke. On 2026-09-01 two of its queries were
changed to derive their state lists from `INVESTIGATING_STATES` and `TERMINAL` rather than
repeat them as literals, and that change reached main untested. These are the tests that
would have caught it wrong.

Marked `integration` and deselected by default: Gate 0 requires `make check` green from a
clean clone, and a clean clone has no Docker. `make test-integration` opts in.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

from faultline.orchestrator.models import (
    INVESTIGATING_STATES,
    TERMINAL,
    Episode,
    Incident,
    IncidentState,
    Severity,
)
from faultline.orchestrator.store import PostgresIncidentStore

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def dsn() -> Iterator[str]:
    with PostgresContainer("pgvector/pgvector:pg16", driver=None) as container:
        yield container.get_connection_url()


@pytest.fixture
def store(dsn: str) -> Iterator[PostgresIncidentStore]:
    with psycopg.connect(dsn) as conn:
        subject = PostgresIncidentStore(conn)
        subject.create_schema()
        with conn.cursor() as cur:
            cur.execute("TRUNCATE incidents, applied_events CASCADE")
        conn.commit()
        yield subject


def an_incident(
    state: IncidentState, *, at: datetime = NOW, resolved: datetime | None = None
) -> Incident:
    episode = Episode(
        episode_key=f"{state.value}@{at.isoformat()}",
        fingerprint=f"fp-{state.value}",
        service="cartservice",
        severity=Severity.CRITICAL,
        alertname="ServiceHighErrorRate",
        starts_at=at,
        attached_at=at,
    )
    return Incident(
        state=state,
        opened_at=at,
        last_activity_at=at,
        resolved_at=resolved,
        episodes={episode.episode_key: episode},
    )


def test_the_schema_applies_twice_without_complaint(store: PostgresIncidentStore) -> None:
    """`CREATE TABLE IF NOT EXISTS` plus `ALTER ... ADD COLUMN IF NOT EXISTS`, as shipped.

    There are no migrations (T2.3's deliverable names them and they do not exist), so
    re-applicability *is* the migration story and it should be asserted rather than assumed.
    """
    store.create_schema()


def test_active_count_counts_exactly_the_states_that_hold_a_slot(
    store: PostgresIncidentStore,
) -> None:
    """The cap's query. One incident in every state; the count must be the slot-holders.

    This is the regression the literal list could not have: it was written when there were
    seven slot-holding states, and would have kept answering seven forever.
    """
    for offset, state in enumerate(IncidentState):
        store.save(an_incident(state, at=NOW + timedelta(seconds=offset)))

    assert store.active_count() == len(INVESTIGATING_STATES)


def test_the_two_states_added_today_hold_a_slot(store: PostgresIncidentStore) -> None:
    """`REJECTED` and `BUDGET_EXHAUSTED` are waiting on a person and are still in flight.

    Under the literal list this replaced, both would have counted as zero and the cap would
    have admitted work past its limit for every incident parked on a human.
    """
    store.save(an_incident(IncidentState.REJECTED))
    store.save(an_incident(IncidentState.BUDGET_EXHAUSTED, at=NOW + timedelta(seconds=1)))

    assert store.active_count() == 2


def test_a_merged_incident_is_not_a_correlation_candidate(
    store: PostgresIncidentStore,
) -> None:
    """`DUPLICATE_MERGED` is terminal with no reopen, so nothing may correlate into it."""
    merged = an_incident(IncidentState.DUPLICATE_MERGED, resolved=NOW)
    store.save(merged)

    candidates = store.correlation_candidates(NOW - timedelta(minutes=30))

    assert merged.id not in {c.id for c in candidates}


def test_a_recently_resolved_incident_is_still_a_candidate(
    store: PostgresIncidentStore,
) -> None:
    """The reopen window, which is the one exception `TERMINAL` must not swallow."""
    reopenable = an_incident(IncidentState.RESOLVED, resolved=NOW)
    stale = an_incident(
        IncidentState.RESOLVED, at=NOW - timedelta(hours=4), resolved=NOW - timedelta(hours=4)
    )
    store.save(reopenable)
    store.save(stale)

    ids = {c.id for c in store.correlation_candidates(NOW - timedelta(minutes=30))}

    assert reopenable.id in ids
    assert stale.id not in ids


def test_every_terminal_state_is_excluded_unless_it_is_a_fresh_resolved(
    store: PostgresIncidentStore,
) -> None:
    for offset, state in enumerate(TERMINAL):
        store.save(an_incident(state, at=NOW + timedelta(seconds=offset), resolved=None))

    candidates = store.correlation_candidates(NOW - timedelta(minutes=30))

    assert candidates == [], "a terminal incident with no resolved_at cannot be reopened into"


def test_queued_returns_only_queued(store: PostgresIncidentStore) -> None:
    store.save(an_incident(IncidentState.QUEUED))
    store.save(an_incident(IncidentState.INVESTIGATING, at=NOW + timedelta(seconds=1)))

    assert [i.state for i in store.queued()] == [IncidentState.QUEUED]


def test_mark_applied_is_idempotent(store: PostgresIncidentStore) -> None:
    """`ON CONFLICT DO NOTHING` - the property the whole redelivery argument rests on."""
    assert not store.already_applied("ep-1", "firing")

    store.mark_applied("ep-1", "firing", "incident-1", NOW)
    store.mark_applied("ep-1", "firing", "incident-1", NOW)

    assert store.already_applied("ep-1", "firing")
    assert not store.already_applied("ep-1", "resolved")
