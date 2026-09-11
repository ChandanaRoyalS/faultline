"""T6.2's ledger against a real Postgres: append-only is a trigger, not a promise.

`PREREGISTRATION-T6.2.md` §2.5: *"the migration ... a test tries both and expects the refusal."*
Marked `integration` like `test_integration_store.py`, for the same reason: `make check` needs no
Docker. CI's `integration` job runs it.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

from faultline.executor.audit import AuditRecord, PostgresAuditStore
from faultline.migrate import upgrade_head

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def dsn() -> Iterator[str]:
    with PostgresContainer("pgvector/pgvector:pg16", driver=None) as container:
        yield container.get_connection_url()


@pytest.fixture
def conn(dsn: str) -> Iterator[psycopg.Connection]:
    upgrade_head(dsn)
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cur:
            # TRUNCATE is not DELETE and the trigger does not fire on it - which is the one
            # statement a test fixture needs and an application role should not be granted.
            cur.execute("TRUNCATE action_audit")
        connection.commit()
        yield connection


def _record(**overrides: object) -> AuditRecord:
    base = dict(
        incident_id="inc-1",
        proposal_id="traj#3",
        action_id="rollback_image",
        target="shippingservice",
        token_id="tok-1",
        caller="test",
        outcome="executed",
        command=["docker", "compose", "up"],
        exit_code=0,
        output_sha256="ab" * 32,
        inverse="re-apply x.yml",
        drift={"drift": {"image": {"running": "a", "declared": "b"}}},
        at=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
    )
    base.update(overrides)
    return AuditRecord(**base)  # type: ignore[arg-type]


def test_a_row_round_trips_with_its_json_columns(conn: psycopg.Connection) -> None:
    store = PostgresAuditStore(conn)
    record = _record()
    store.append(record)

    [back] = store.for_incident("inc-1")
    assert back.id == record.id and back.command == ["docker", "compose", "up"]
    assert back.drift == record.drift and back.inverse == "re-apply x.yml"


def test_update_and_delete_are_refused_by_the_database(conn: psycopg.Connection) -> None:
    """Whoever the caller is: this connection has every privilege the executor's has."""
    store = PostgresAuditStore(conn)
    record = _record()
    store.append(record)

    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"),
        conn.cursor() as cur,
    ):
        cur.execute("UPDATE action_audit SET outcome = 'refused' WHERE id = %s", (record.id,))
    conn.rollback()
    with (
        pytest.raises(psycopg.errors.InsufficientPrivilege, match="append-only"),
        conn.cursor() as cur,
    ):
        cur.execute("DELETE FROM action_audit WHERE id = %s", (record.id,))
    conn.rollback()

    [still] = store.for_incident("inc-1")
    assert still.outcome == "executed"


def test_spent_finds_the_consuming_row_and_ignores_refusals(conn: psycopg.Connection) -> None:
    store = PostgresAuditStore(conn)
    store.append(_record(outcome="approved", id="r0"))
    store.append(_record(outcome="refused", id="r1", reason="kill switch"))
    assert store.spent("tok-1") is None
    store.append(_record(outcome="executed", id="r2"))
    assert store.spent("tok-1").id == "r2"
    assert store.spent("tok-other") is None
