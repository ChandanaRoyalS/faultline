# ADR-0033 — migrations

**Status:** accepted, 2026-09-01
**Task:** T2.3 (*"migrations from day one"*), with the tool named by the proposal

## Context

Four modules each carried a `SCHEMA` constant and applied it themselves:
`orchestrator/store.py`, `agents/trajectory.py`, `context/store.py`, `tools/changes.py`. Every
statement was `CREATE TABLE IF NOT EXISTS` or `ADD COLUMN IF NOT EXISTS`, and each module's
`create_schema()` ran on process start.

That is not a migration system; it is a set of statements that happen to be safe to repeat.
It can add a table and add a column. It cannot rename, cannot change a type, cannot drop,
cannot backfill, and cannot order a change in one module against a change in another. It held
for as long as it did because every change so far has been additive — which is a fact about
this project's history, not a property of the design.

It has already failed twice.

**T7.9.** Two columns were added to `trajectory_retrievals`' `CREATE`. The table existed, so
the `CREATE` did nothing, the columns never arrived, and the first investigation against that
store died on `UndefinedColumn`, discarding a scenario. The fix was a convention — *"a column
added to a `CREATE` after the table ships must also appear in an idempotent `ALTER`"* — and a
test to enforce it. A convention plus a test is what you write when you have no mechanism.

**2026-09-01.** `ALTER TABLE incident_episodes ADD COLUMN` stood *above* the
`CREATE TABLE incident_episodes` it depended on. Every machine that had ever run it already
had the table, because the table predates the column, so it worked everywhere it had ever been
run. A fresh database could not have started the orchestrator. It was found the day T2.3's
integration tests built a schema from nothing for the first time.

## Decision

Alembic, one revision history, for one database.

**Revision 0001 was generated, not transcribed.** A one-off script read the four `SCHEMA`
constants and wrote them into the revision as literals, in dependency order. Retyping 150
lines of DDL is how a difference nobody notices gets introduced, and the difference would have
been invisible: both paths would work, on different schemas.

**The equivalence was proved before anything was deleted.** Two databases in one container —
one built by the four `create_schema()` calls, one by `alembic upgrade head` — compared over
`information_schema.columns` and `pg_indexes`. **85 columns and 17 indexes, identical.** The
only difference was Alembic's own `alembic_version` table.

**The constants are deleted.** Keeping them would leave two descriptions of one schema, and
the whole failure mode above is what happens when the description and the database disagree.
`tests/test_runner.py` now asserts that no module defines a `SCHEMA` at all, which is a
stronger invariant than the convention it replaces.

**No autogenerate, and no `target_metadata`.** This project's schema is raw SQL rather than
SQLAlchemy models, so autogenerate is unavailable by construction. Every revision is written
by hand. Recorded so nobody later reads its absence as an oversight.

**Revision 0001 has no `downgrade`.** Its downgrade is an empty database, and expressing that
as a `DROP` cascade would put a one-command way to destroy an incident record in the tree in
exchange for nothing anyone needs.

**The DSN is passed, not configured twice.** `alembic.ini` has no `sqlalchemy.url`; `env.py`
takes the DSN from `Config.attributes` when `faultline.migrate` passes one and from
`OrchestratorSettings` otherwise. A migration pointed at the wrong database is not a failure
anyone notices quickly.

## Consequences

`--create-schema` on the orchestrator and context CLIs now applies the **whole** schema rather
than that module's subset. That is the intended change — one database has one schema — but it
is a behaviour change and is recorded as one.

An existing database needs `faultline-migrate --stamp` once. Its tables already match revision
0001; stamping records that without running anything, and an integration test proves stamping
creates nothing.

**The image had to change.** `faultline.migrate.ini_path()` walks up from the installed package
for `alembic.ini`, and the Dockerfile copied only `src`. The same was true of
`knowledge/allowlist.yaml` from ADR-0032, added hours earlier: both resolved in a clone and in
neither container. `tests/test_packaging.py` now asserts that anything the runtime finds by
walking up is copied into the image, and the fix was verified by running both loaders inside a
built container.

**What this does not yet prove.** Every revision in the history is additive, because there is
only one and it is the initial state. The first non-additive migration — a rename, a type
change, a backfill — is the one that will exercise this properly, and it does not exist yet.
