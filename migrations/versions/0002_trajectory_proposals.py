"""The proposer's table (T3.9).

Revision ID: 0002
Revises: 0001

ADR-0028 §6 asked for this table and for the `ALTER` beside the `CREATE`, *"because the
in-memory double the tests use will not catch its absence"* - the lesson T7.10 learned when a
scenario died on `UndefinedColumn` against a database the tests never touch. Migrations arrived
at T2.3, so the `ALTER` is no longer how a deployment gains a column; the caution behind it
stands, and `tests/test_integration_store.py` exercises this table against real Postgres.

**Why a table rather than the step payload alone.** The proposal is already written into
`trajectory_steps.payload` as JSON, and that is what a replay reads. This table exists because
T4.2 scores proposals on three axes - class, target, grounding - and a scorer that must unpack
JSONB to group by remediation class is a scorer nobody will write the second query for. The
columns here are exactly the scored fields; everything else stays in the payload.
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
    CREATE TABLE IF NOT EXISTS trajectory_proposals (
        trajectory_id      TEXT NOT NULL,
        seq                INT  NOT NULL,
        -- 'none' is an abstention, which is an outcome and not an absence (ADR-0022 s1.2).
        remediation_class  TEXT NOT NULL,
        -- Empty for an abstention. Otherwise an allowlist id and a canonical service name.
        action_id          TEXT NOT NULL DEFAULT '',
        target             TEXT NOT NULL DEFAULT '',
        rests_on           JSONB NOT NULL DEFAULT '[]'::jsonb,
        expected_effect    TEXT NOT NULL,
        confirm_within_seconds INT NOT NULL,
        if_wrong           TEXT NOT NULL,
        risk               TEXT NOT NULL,
        blast_radius       TEXT NOT NULL,
        -- False when the proposal was refused at the grounding boundary and kept for the
        -- record. A refused proposal is evidence about the run, so it is stored, not dropped.
        accepted           BOOLEAN NOT NULL DEFAULT TRUE,
        PRIMARY KEY (trajectory_id, seq),
        FOREIGN KEY (trajectory_id) REFERENCES trajectories(id) ON DELETE CASCADE
    );

    -- The scoring query: every proposal of a class, across runs.
    CREATE INDEX IF NOT EXISTS trajectory_proposals_class_idx
        ON trajectory_proposals (remediation_class);

    -- Beside the CREATE, per ADR-0028 s6: a deployment that already made this table by hand
    -- gains the columns rather than failing on the first INSERT that names them.
    ALTER TABLE trajectory_proposals ADD COLUMN IF NOT EXISTS risk TEXT NOT NULL DEFAULT '';
    ALTER TABLE trajectory_proposals
        ADD COLUMN IF NOT EXISTS blast_radius TEXT NOT NULL DEFAULT '';
    ALTER TABLE trajectory_proposals
        ADD COLUMN IF NOT EXISTS accepted BOOLEAN NOT NULL DEFAULT TRUE;
    """
    )
