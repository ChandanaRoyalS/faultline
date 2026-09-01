"""Alembic environment.

No `target_metadata`: this project's schema is raw SQL rather than SQLAlchemy models, so
autogenerate is unavailable by construction and every revision is written by hand. That is
the right trade here - the DDL is already the artifact under review - and it is recorded so
nobody later assumes autogenerate was forgotten.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from faultline.orchestrator.settings import OrchestratorSettings


def url() -> str:
    # `faultline.migrate` passes the caller's DSN here; the settings object is the
    # fallback for a bare `alembic` invocation from the shell.
    dsn: str = context.config.attributes.get("dsn") or OrchestratorSettings().postgres_dsn
    # SQLAlchemy resolves a bare `postgresql://` to psycopg2, which this project does not
    # install. psycopg 3 is the driver everywhere else, so name it rather than depend on a
    # default that would fail at connect time with a missing-module error.
    return dsn.replace("postgresql://", "postgresql+psycopg://", 1)


def run_offline() -> None:
    context.configure(url=url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    engine = create_engine(url())
    try:
        with engine.connect() as connection:
            context.configure(connection=connection)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
