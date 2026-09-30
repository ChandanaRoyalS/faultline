"""The SQL corruption, executed rather than inspected: a real Postgres, a real `docker exec psql`.

R4 (2026-09-24) ran a corruption loop that never executed its command while every fake-runner
test passed; the valkey sweep's contract with `sh -c` is tested by running it. This is the same
bar for A10's tool: a table with the world catalog's column types, corrupted and restored by the
handler through the real Docker CLI, read back over a separate connection at each step - and,
where `world-v2/` is checked out, the world's own catalog from its init script. Marked
`integration` like `test_integration_executor.py`, for the same reason: `make check` needs no
Docker.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

from evalharness.scenario import FaultClass
from injector.docker import DockerCli, SubprocessRunner
from injector.faults import DatastoreCorruptionFault, FaultUsageError
from injector.models import FaultDefinition, SqlCorruptionRestore

pytestmark = pytest.mark.integration

INIT_SQL = Path(__file__).parent.parent / "world-v2" / "src" / "postgresql" / "init.sql"

SHIPPED = "f9b57aae49e7ad4305e3120a54fdc20d"
"""The catalog's fingerprint as shipped: what A10's inject printed on the world before its write
(and what its restore printed after)."""


TABLE = """
CREATE SCHEMA catalog;
CREATE TABLE catalog.products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);
INSERT INTO catalog.products (id, name, description) VALUES
    ('A1', 'plain', 'A telescope.'),
    ('B2', 'quotes', 'It''s a "scope" | with a pipe'),
    ('C3', 'lines', E'two\nlines and a tab\there'),
    ('D4', 'dollars', 'costs $5, $$ and $tag$'),
    ('E5', 'unicode', 'Sternwarte für Anfänger');
"""
"""The world's catalog column types, with values chosen to break any quoting the restore gets
wrong. The world's own rows are exercised by the last test when `world-v2/` is checked out."""


@pytest.fixture
def db() -> Iterator[tuple[str, str]]:
    """(container name, dsn) of a fresh Postgres holding TABLE."""
    with PostgresContainer("pgvector/pgvector:pg16", driver=None) as container:
        dsn = container.get_connection_url()
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(TABLE)
        yield container.get_wrapped_container().name, dsn


def _definition(container: str, **overrides: object) -> FaultDefinition:
    params: dict[str, object] = {
        "table": "catalog.products",
        "column": "description",
        "key": "id",
        "database": "test",
        "user": "test",
    }
    params.update(overrides)
    return FaultDefinition(
        id="pg-corrupt",
        fault_class=FaultClass.DATASTORE_CORRUPTION,
        target=container,
        description="t",
        params=params,  # type: ignore[arg-type]
    )


def _column(dsn: str, column: str = "description") -> dict[str, str | None]:
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(f"SELECT id, {column} FROM catalog.products").fetchall()
    return {row[0]: row[1] for row in rows}


def test_the_handler_corrupts_the_table_and_puts_it_back_exactly(db: tuple[str, str]) -> None:
    container, dsn = db
    before = _column(dsn)
    assert len(before) == 5 and all(before.values())
    handler = DatastoreCorruptionFault(DockerCli(SubprocessRunner()))

    outcome = handler.inject(_definition(container))

    assert isinstance(outcome.restore, SqlCorruptionRestore)
    assert outcome.restore.saved == before, "every value, byte for byte, in the state"
    assert _column(dsn) == dict.fromkeys(before)

    with pytest.raises(FaultUsageError, match="not at rest"):
        handler.inject(_definition(container))
    assert _column(dsn) == dict.fromkeys(before), "the refused second run wrote nothing"

    changes = handler.restore(outcome.restore)
    assert _column(dsn) == before
    assert outcome.restore.fingerprint in changes[0]
    handler.restore(outcome.restore)  # idempotent: the same values over the same values
    assert _column(dsn) == before


def test_a_not_null_column_is_refused_and_nothing_changes(db: tuple[str, str]) -> None:
    container, dsn = db
    names = _column(dsn, "name")
    handler = DatastoreCorruptionFault(DockerCli(SubprocessRunner()))
    with pytest.raises(FaultUsageError, match="NOT been injected"):
        handler.inject(_definition(container, column="name"))
    assert _column(dsn, "name") == names


def test_the_worlds_own_catalog_fingerprints_as_a10_printed() -> None:
    """The world's init script, loaded as the world loads it, through the handler: the saved
    fingerprint is the one A10's inject printed on the running world before its write."""
    if not INIT_SQL.exists():
        pytest.skip("world-v2's source is not checked out here (it is .gitignored)")
    with PostgresContainer("pgvector/pgvector:pg16", driver=None) as container:
        dsn = container.get_connection_url()
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(INIT_SQL.read_text())
        name = container.get_wrapped_container().name
        handler = DatastoreCorruptionFault(DockerCli(SubprocessRunner()))
        outcome = handler.inject(_definition(name))
        assert isinstance(outcome.restore, SqlCorruptionRestore)
        assert outcome.restore.fingerprint == SHIPPED
        assert len(outcome.restore.saved) == 10
        handler.restore(outcome.restore)
        assert all(_column(dsn).values())
