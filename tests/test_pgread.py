"""`pgread.reading`: a read ends its own transaction (found by the T6.6 rollout, 2026-09-18).

The deployment's `faultline-migrate` waited 46 minutes on `ALTER TABLE trajectories` because the
API's connection - last statement, `/metrics`'s token sum - and the orchestrator's - last
statement, its `queued()` poll - were each idle in transaction since their process started,
holding share locks on every table they had read. These tests hold every read path to the rule;
`tests/test_integration_store.py` asserts the real connection is idle after each read.
"""

from __future__ import annotations

from typing import Any

import pytest

from faultline.pgread import reading


class _Cursor:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows = rows or []
        self.executed: list[str] = []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *exc: object) -> None:
        pass

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append(sql)

    def fetchone(self) -> Any:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[Any]:
        return list(self.rows)


class _Connection:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows = rows or []
        self.rollbacks = 0
        self.commits = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self.rows)

    def rollback(self) -> None:
        self.rollbacks += 1

    def commit(self) -> None:
        self.commits += 1


def test_a_read_rolls_back_once_when_the_block_ends() -> None:
    conn = _Connection([(1,)])

    with reading(conn) as cur:
        cur.execute("SELECT 1")
        assert conn.rollbacks == 0, "not before the caller has read its rows"

    assert conn.rollbacks == 1 and conn.commits == 0


def test_a_read_that_raises_still_ends_its_transaction() -> None:
    """The exception path is the one that leaves a connection idle-in-transaction forever in
    code that rolls back only on the happy path."""
    conn = _Connection()

    with pytest.raises(RuntimeError), reading(conn) as cur:
        cur.execute("SELECT 1")
        raise RuntimeError("mid-read")

    assert conn.rollbacks == 1


def test_a_connection_without_rollback_is_tolerated() -> None:
    """Test fakes that only offer `cursor()` keep working; the rule is enforced on real
    connections by the integration test, not by refusing stubs."""

    class Bare:
        def cursor(self) -> _Cursor:
            return _Cursor([(7,)])

    with reading(Bare()) as cur:
        assert cur.fetchone() == (7,)


# --- every read path uses it ---------------------------------------------------------------------


def test_the_metrics_snapshot_ends_its_transaction() -> None:
    """**The one that blocked the migration.** Three SELECTs per scrape, and the first version
    committed none of them, so the first scrape after start held `trajectories` for the life of
    the API process."""
    from faultline.observability import metrics

    class Queue:
        def queued(self) -> list[Any]:
            return []

        def active_count(self) -> int:
            return 0

    class Cur(_Cursor):
        def fetchall(self) -> list[Any]:
            return []

        def fetchone(self) -> Any:
            if "FILTER" in (self.executed[-1] if self.executed else ""):
                return [0] * (len(metrics.DURATION_BUCKETS_SECONDS) + 2)
            return (0, 0)

    class Conn(_Connection):
        def cursor(self) -> _Cursor:
            return Cur()

    conn = Conn()
    metrics.snapshot(Queue(), conn, usd_per_mtok=(5.0, 25.0))

    assert conn.rollbacks == 1


def test_the_incident_store_s_reads_end_their_transactions() -> None:
    """The orchestrator's `queued()` poll was the other 46-minute holder."""
    from faultline.orchestrator.store import PostgresIncidentStore

    conn = _Connection([])
    store = PostgresIncidentStore(conn)

    store.queued()
    store.active_count()
    store.get("inc-1")

    assert conn.rollbacks == 3 and conn.commits == 0


def test_the_trajectory_store_s_reads_end_their_transactions() -> None:
    from faultline.agents.trajectory import PostgresTrajectoryStore

    conn = _Connection([])
    store = PostgresTrajectoryStore(conn)

    assert store.get("traj-1") is None
    assert store.latest_for_incident("inc-1") is None
    assert store.envelope("tr_1") is None

    assert conn.rollbacks == 3


def test_the_acceptance_ledger_s_reads_end_their_transactions() -> None:
    from faultline.context.acceptance import PostgresAcceptanceStore

    conn = _Connection([])
    store = PostgresAcceptanceStore(conn)

    assert store.accepted("s", "d") is None
    assert store.callers() == []

    assert conn.rollbacks == 2


def test_no_postgres_store_reads_through_a_bare_cursor() -> None:
    """The rule in source: a `SELECT` under `with self._conn.cursor()` in a read method is the
    shape that produced the lock. Write methods keep the bare cursor and their `commit()`."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src" / "faultline"
    offenders: list[str] = []
    for path in (
        root / "orchestrator" / "store.py",
        root / "agents" / "trajectory.py",
        root / "context" / "acceptance.py",
        root / "observability" / "metrics.py",
    ):
        source = path.read_text()
        bare = r"with (?:self\._conn|connection)\.cursor\(\) as cur:\n((?:.*\n){1,3})"
        for match in re.finditer(bare, source):
            body = match.group(1)
            if "SELECT" in body and "INSERT" not in body and "UPDATE" not in body:
                offenders.append(f"{path.name}: {body.strip().splitlines()[0][:70]}")
    assert not offenders, offenders
