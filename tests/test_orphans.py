"""Q72: a killed investigation's trajectory row is closed as `orphaned`, not left as `running`.

The first scrape of `/metrics` (2026-09-18) read four rows with no outcome in a process where the
in-memory gauge said nothing was running - trajectories whose process died with the sweep that
launched them. Nothing reconciled them. Now the sweep does, before it starts, and
`faultline-eval-db orphans` does by hand.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from faultline.agents.trajectory import (
    ORPHAN_OUTCOME,
    InMemoryTrajectoryStore,
    PostgresTrajectoryStore,
    Trajectory,
    orphan_ceiling_seconds,
)

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def _trajectory(started_ago: int, outcome: str | None) -> Trajectory:
    t = Trajectory(
        incident_id="i", model="m", effort="e", started_at=NOW - timedelta(seconds=started_ago)
    )
    t.outcome = outcome
    return t


def test_the_ceiling_is_twice_the_wall_clock_budget() -> None:
    """A run inside its budget may be slow; one past twice it has no process left to finish it -
    `Budget.wall_clock_seconds` would have stopped a live one long before."""
    from faultline.agents.budget import Budget

    assert orphan_ceiling_seconds() == 2 * Budget().wall_clock_seconds == 1200


def test_only_old_rows_with_no_outcome_are_closed_and_they_are_named() -> None:
    """**Names, does not guess.** Two facts about the row - no outcome, and older than the
    ceiling - and one new value. A recent row with no outcome is a run in flight and is left; a
    row with any outcome is finished business, however old."""
    store = InMemoryTrajectoryStore()
    stale = _trajectory(1300, None)
    recent = _trajectory(300, None)
    failed = _trajectory(5000, "failed")
    done = _trajectory(5000, "dispatched")
    for t in (stale, recent, failed, done):
        store.save(t)

    closed = store.close_orphans(older_than_seconds=1200, now=NOW)

    assert closed == [stale.id]
    assert stale.outcome == ORPHAN_OUTCOME
    assert recent.outcome is None and failed.outcome == "failed" and done.outcome == "dispatched"


def test_orphaned_is_its_own_value_not_failed() -> None:
    """These did not raise; they were killed. A dashboard over `outcome` should be able to tell
    a run that failed from one whose sweep died under it."""
    assert ORPHAN_OUTCOME == "orphaned"
    assert ORPHAN_OUTCOME not in {"failed", "dispatched", "budget_exhausted", "running"}


def test_a_second_pass_closes_nothing() -> None:
    store = InMemoryTrajectoryStore()
    store.save(_trajectory(1300, None))

    first = store.close_orphans(older_than_seconds=1200, now=NOW)
    second = store.close_orphans(older_than_seconds=1200, now=NOW)

    assert len(first) == 1 and second == []


def test_the_postgres_store_issues_one_update_by_the_same_two_facts_and_commits() -> None:
    """The SQL is the predicate in the test above, and it leaves `ended_at` alone: the row does
    not know when it died, and a made-up end would put a made-up duration in the histogram."""
    executed: list[tuple[str, Any]] = []

    class Cur:
        def __enter__(self) -> Cur:
            return self

        def __exit__(self, *exc: object) -> None:
            pass

        def execute(self, sql: str, params: Any) -> None:
            executed.append((sql, params))

        def fetchall(self) -> list[tuple[str]]:
            return [("b",), ("a",)]

    class Conn:
        commits = 0

        def cursor(self) -> Cur:
            return Cur()

        def commit(self) -> None:
            Conn.commits += 1

    closed = PostgresTrajectoryStore(Conn()).close_orphans(older_than_seconds=1200, now=NOW)

    assert closed == ["a", "b"]
    sql, params = executed[0]
    assert sql.startswith("UPDATE trajectories SET outcome = %s")
    assert "outcome IS NULL" in sql and "started_at <" in sql and "RETURNING id" in sql
    assert "ended_at" not in sql
    assert params == (ORPHAN_OUTCOME, NOW, 1200)
    assert Conn.commits == 1, "a write commits; this is not a read"


def test_the_sweep_reconciles_before_it_starts_and_eval_db_offers_it_by_hand() -> None:
    """The sweep is the process that kills them, so it is the process that closes them - beside
    `faultline-inject stop --all`, the same cleanup for the world."""
    import inspect

    from evalharness import evaldb, sweep

    assert "_close_orphans(dsn)" in inspect.getsource(sweep.main)
    assert "close_orphans" in inspect.getsource(sweep._close_orphans)
    assert '"orphans"' in inspect.getsource(evaldb.main)
