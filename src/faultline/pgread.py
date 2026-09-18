"""A read that ends its own transaction.

## The defect this replaces

`psycopg` connections open a transaction on the first statement and hold it until `commit()` or
`rollback()`. Every store here calls `commit()` after a write and nothing after a read, so a
process that only reads - or reads and then waits - sits **idle in transaction** for as long as it
lives, holding `ACCESS SHARE` on every table it touched. That lock is compatible with everything
except DDL, which is why nobody saw it until the first migration ran against a live deployment.

**2026-09-18, the T6.6 rollout.** `faultline-migrate` reached 0010 - `ALTER TABLE trajectories ADD
COLUMN trace_id` - and waited 46 minutes for a lock. `pg_stat_activity` named the holders: the API's
connection, whose last statement was `/metrics`'s token sum (piece 3 read three tables on every
scrape and committed nothing, so the first scrape after start held `trajectories` for the life of
the process), and the orchestrator's, whose last statement was its `queued()` poll. The metrics
surface built to watch the platform blocked the migration that gives the trajectory its trace id.
Terminating both backends released the migration; this module is so that never has to be done
again.

## The rule

A read path takes its cursor through `reading(connection)`, which rolls the transaction back when
the block ends - success or exception - so the connection returns to idle and holds nothing. A
rollback after a `SELECT` discards nothing. Write paths keep their explicit `commit()`; a rollback
after a read that a caller meant to follow with a write in the *same* transaction would be wrong,
and no path here does that (`grep -rn "FOR UPDATE" src/` is empty).

Fakes in tests without a `rollback` are tolerated, so a store can still be exercised against a
cursor stub; the integration store test asserts the real thing - `transaction_status` is idle
after every read.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def reading(connection: Any) -> Iterator[Any]:
    """A cursor for a read-only block. The transaction it opens ends with the block."""
    try:
        with connection.cursor() as cur:
            yield cur
    finally:
        rollback = getattr(connection, "rollback", None)
        if rollback is not None:
            rollback()
