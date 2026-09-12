"""The rejection ledger (T6.3).

Revision ID: 0006
Revises: 0005

`incident_rejections` is one row per rejected proposal - who rejected it, which proposal, and
**why**, which T2.3 has required since Phase 2 (*"`REJECTED` exits to targeted re-investigation,
reason required"*) without anywhere to put it. `evals/runs/PREREGISTRATION-T6.3.md` §2.2 registers
it as a table rather than a column on `incidents`: a column holds the latest reason and silently
loses the one before it, and the count of rows is what the re-investigation cap reads.

Append-only at the database on migration 0005's pattern, and for the same reason. The reason text
is the input an operator gave to a machine that then spent money on their behalf; a ledger whose
rows can be edited afterwards cannot answer *what were we told at the time*.
"""

from __future__ import annotations

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
    CREATE TABLE IF NOT EXISTS incident_rejections (
        id           TEXT PRIMARY KEY,
        at           TIMESTAMPTZ NOT NULL,
        incident_id  TEXT NOT NULL,
        -- <trajectory>#<seq>, the same identifier the approval path mints against, so a
        -- rejection and an approval of the same proposal are comparable rows.
        proposal_id  TEXT NOT NULL DEFAULT '',
        action_id    TEXT NOT NULL DEFAULT '',
        target       TEXT NOT NULL DEFAULT '',
        reason       TEXT NOT NULL,
        caller       TEXT NOT NULL
    );

    -- "How many times has this incident been rejected" is the cap, and it is one indexed count.
    CREATE INDEX IF NOT EXISTS incident_rejections_incident_idx
        ON incident_rejections (incident_id, at);

    CREATE OR REPLACE FUNCTION incident_rejections_is_append_only() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'incident_rejections is append-only: % is not permitted (T6.3)', TG_OP
            USING ERRCODE = 'insufficient_privilege';
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS incident_rejections_no_update ON incident_rejections;
    CREATE TRIGGER incident_rejections_no_update
        BEFORE UPDATE OR DELETE ON incident_rejections
        FOR EACH ROW EXECUTE FUNCTION incident_rejections_is_append_only();
    """
    )


def downgrade() -> None:
    op.execute(
        """
    DROP TRIGGER IF EXISTS incident_rejections_no_update ON incident_rejections;
    DROP FUNCTION IF EXISTS incident_rejections_is_append_only();
    DROP TABLE IF EXISTS incident_rejections;
    """
    )
