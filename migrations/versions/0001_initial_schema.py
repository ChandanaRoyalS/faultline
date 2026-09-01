"""The schema as it stood when migrations arrived.

Revision ID: 0001
Revises:

**Generated, not transcribed.** T2.3 asks for "migrations from day one" and this project
reached Phase 7 without them, so day one is late and the schema already exists in four
modules' `CREATE TABLE IF NOT EXISTS` blocks. This revision was produced by reading those
four constants and writing them here verbatim, in dependency order, because retyping 150
lines of DDL is how a difference nobody notices gets introduced. The constants were deleted
in the same change; this file is now the only place the initial schema exists.

Every revision after this one is ordinary hand-written DDL. There is no `downgrade`: the
initial revision's downgrade is an empty database, and expressing that as a DROP cascade
would offer a one-command way to destroy a production incident record in exchange for
nothing anyone needs.
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- orchestrator - incidents, episodes, applied events ---
    op.execute(
        """
    CREATE TABLE IF NOT EXISTS incidents (
        id                       TEXT PRIMARY KEY,
        state                    TEXT        NOT NULL,
        severity                 TEXT        NOT NULL,
        opened_at                TIMESTAMPTZ NOT NULL,
        last_activity_at         TIMESTAMPTZ NOT NULL,
        resolved_at              TIMESTAMPTZ,
        resolution               TEXT,
        state_before_resolution  TEXT,
        investigation_id         TEXT
    );

    -- Added at T3.5 rather than in the original CREATE, so an existing deployment gains it
    -- without a migration tool. The runner writes it; nothing before T3.5 had an id to write.
    ALTER TABLE incidents ADD COLUMN IF NOT EXISTS investigation_id TEXT;

    CREATE TABLE IF NOT EXISTS incident_episodes (
        incident_id   TEXT        NOT NULL REFERENCES incidents(id),
        episode_key   TEXT        NOT NULL,
        fingerprint   TEXT        NOT NULL,
        service       TEXT,
        severity      TEXT        NOT NULL,
        alertname     TEXT,
        starts_at     TIMESTAMPTZ NOT NULL,
        ends_at       TIMESTAMPTZ,
        attached_at   TIMESTAMPTZ NOT NULL,
        resolved_at   TIMESTAMPTZ,
        join_rule     TEXT,
        PRIMARY KEY (incident_id, episode_key)
    );

    -- ADR-0017 deferred this to "whoever builds that reporting", which is T4.1. Per episode
    -- rather than per incident: a join is a decision about an episode, and an incident
    -- accumulates several. See `Episode.join_rule`.
    --
    -- **This ALTER used to stand above the CREATE**, where it raised `UndefinedTable` on any
    -- database that did not already have the table. Every machine this had run on did, because
    -- the table predates the column - so the bug was invisible until T2.3's integration tests
    -- built a schema from nothing, which is the first time that had ever happened.
    ALTER TABLE incident_episodes ADD COLUMN IF NOT EXISTS join_rule TEXT;

    -- Stream redelivery, not Alertmanager repeats. Ingest already suppresses the latter
    -- (ADR-0015); this suppresses an event published once and delivered twice, and it keys on
    -- the same identity so nothing new had to be invented for it.
    CREATE TABLE IF NOT EXISTS applied_events (
        episode_key TEXT        NOT NULL,
        status      TEXT        NOT NULL,
        incident_id TEXT        NOT NULL,
        applied_at  TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (episode_key, status)
    );

    CREATE INDEX IF NOT EXISTS incidents_state_idx ON incidents (state);
    CREATE INDEX IF NOT EXISTS incidents_resolved_at_idx ON incidents (resolved_at);
    """
    )

    # --- agents - trajectories, steps, tool calls, retrievals ---
    op.execute(
        """
    CREATE TABLE IF NOT EXISTS trajectories (
        id               TEXT PRIMARY KEY,
        incident_id      TEXT        NOT NULL,
        model            TEXT        NOT NULL,
        role_models      JSONB       NOT NULL DEFAULT '{}'::jsonb,
        effort           TEXT        NOT NULL,
        runtime_version  TEXT        NOT NULL DEFAULT '',
        started_at       TIMESTAMPTZ NOT NULL,
        ended_at         TIMESTAMPTZ,
        outcome          TEXT,
        budget_exhausted BOOLEAN     NOT NULL DEFAULT FALSE
    );

    CREATE TABLE IF NOT EXISTS trajectory_steps (
        trajectory_id TEXT        NOT NULL REFERENCES trajectories(id) ON DELETE CASCADE,
        seq           INT         NOT NULL,
        role          TEXT        NOT NULL,
        kind          TEXT        NOT NULL,
        at            TIMESTAMPTZ NOT NULL,
        tokens_in     INT         NOT NULL DEFAULT 0,
        tokens_out    INT         NOT NULL DEFAULT 0,
        latency_ms    INT         NOT NULL DEFAULT 0,
        payload       JSONB       NOT NULL DEFAULT '{}'::jsonb,
        PRIMARY KEY (trajectory_id, seq)
    );

    -- The envelope is TEXT and is never normalised on the way in or out. It carries ANSI escapes
    -- and a per-call nonce in its closing delimiter, and a replay that reads back anything other
    -- than the exact bytes is replaying a different prompt (ADR-0020 §3).
    CREATE TABLE IF NOT EXISTS trajectory_tool_calls (
        trajectory_id  TEXT NOT NULL,
        seq            INT  NOT NULL,
        tool           TEXT NOT NULL,
        request        JSONB NOT NULL DEFAULT '{}'::jsonb,
        result_id      TEXT NOT NULL,
        envelope       TEXT NOT NULL,
        envelope_sha256 TEXT NOT NULL,
        PRIMARY KEY (trajectory_id, seq),
        FOREIGN KEY (trajectory_id, seq) REFERENCES trajectory_steps(trajectory_id, seq)
            ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS trajectory_tool_calls_result_idx
        ON trajectory_tool_calls (result_id);

    -- exclude_origin is nullable because the product case has nothing to exclude. Every benchmark
    -- retrieval sets it, and this is the column T4.1b reads to assert the filter fired (ADR-0008).
    CREATE TABLE IF NOT EXISTS trajectory_retrievals (
        trajectory_id  TEXT NOT NULL,
        seq            INT  NOT NULL,
        query          TEXT NOT NULL,
        k              INT  NOT NULL,
        exclude_origin TEXT,
        returned       JSONB NOT NULL DEFAULT '[]'::jsonb,
        scores         JSONB NOT NULL DEFAULT '[]'::jsonb,
        -- The retrieved lines as the model read them (T7.9). Empty for rows written before it,
        -- and that emptiness is the honest record: their retrieved text is gone, not recoverable.
        rendered       JSONB NOT NULL DEFAULT '[]'::jsonb,
        rendered_sha256 TEXT,
        PRIMARY KEY (trajectory_id, seq),
        FOREIGN KEY (trajectory_id, seq) REFERENCES trajectory_steps(trajectory_id, seq)
            ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS trajectories_incident_idx ON trajectories (incident_id);

    -- Additive columns must ALTER as well as appear above. `CREATE TABLE IF NOT EXISTS` does
    -- nothing to a table that already exists, so a column added to the CREATE never reaches a
    -- database created before it - which is exactly how T7.9's `rendered` shipped and then failed
    -- the first investigation run against a live store, mid-sweep. `create_schema` is called on
    -- every start, so these run every time and must stay idempotent.
    ALTER TABLE trajectory_retrievals
        ADD COLUMN IF NOT EXISTS rendered JSONB NOT NULL DEFAULT '[]'::jsonb;
    ALTER TABLE trajectory_retrievals ADD COLUMN IF NOT EXISTS rendered_sha256 TEXT;
    """
    )

    # --- context - pgvector and the incident chunk corpus ---
    op.execute(
        """
    -- pgvector is not in postgres:16-alpine. docker-compose.yml runs pgvector/pgvector:pg16,
    -- which is a free change: the platform compose file is NOT one of the three inputs to
    -- world.compose_digest (ADR-0014), so editing it invalidates no bundle. See ADR-0018.
    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE IF NOT EXISTS incident_chunks (
        id                    TEXT PRIMARY KEY,
        document_id           TEXT   NOT NULL,
        section               TEXT   NOT NULL,
        section_index         INT    NOT NULL,
        body                  TEXT   NOT NULL,

        -- Provenance. ADR-0008's axis 2 is `origin`; the rest is what makes a stale or
        -- mislabelled chunk detectable rather than merely present.
        origin                TEXT   NOT NULL,
        split                 TEXT   NOT NULL,
        scenario_id           TEXT   NOT NULL,
        fault_class           TEXT   NOT NULL,
        scenario_fingerprint  TEXT   NOT NULL,
        recorded_from         TEXT   NOT NULL,
        title                 TEXT   NOT NULL,
        source_path           TEXT   NOT NULL,

        -- Which model produced the vector beside it. Two embedders' vectors are not comparable,
        -- and a model swap that left them mixed would degrade retrieval silently.
        embedder              TEXT   NOT NULL,
        dimensions            INT    NOT NULL,
        embedding             vector NOT NULL,

        body_tsv              tsvector GENERATED ALWAYS AS (to_tsvector('english', body)) STORED
    );

    CREATE INDEX IF NOT EXISTS incident_chunks_origin_idx ON incident_chunks (origin);
    CREATE INDEX IF NOT EXISTS incident_chunks_split_idx  ON incident_chunks (split);
    CREATE INDEX IF NOT EXISTS incident_chunks_tsv_idx    ON incident_chunks USING GIN (body_tsv);
    """
    )

    # --- tools - the change record log ---
    op.execute(
        """
    CREATE TABLE IF NOT EXISTS change_records (
        id        TEXT PRIMARY KEY,
        service   TEXT        NOT NULL,
        at        TIMESTAMPTZ NOT NULL,
        actor     TEXT        NOT NULL,
        resource  TEXT        NOT NULL,
        action    TEXT        NOT NULL,
        summary   TEXT        NOT NULL,
        before    TEXT,
        after     TEXT
    );

    CREATE INDEX IF NOT EXISTS change_records_service_at_idx ON change_records (service, at);
    """
    )


def downgrade() -> None:
    raise NotImplementedError("the initial revision does not drop the schema - see the docstring")
