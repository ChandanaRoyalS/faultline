"""The severity-1 acknowledgment gate's ledger (T6.3).

Revision ID: 0007
Revises: 0006

`incident_acknowledgements` is one row per person who took ownership of a critical incident before
anything could be approved on it. The plan's deliverable names a *"sev-1 ack gate"*;
`evals/runs/PREREGISTRATION-T6.3.md` §2.5 says what the gate refuses and when.

**Its own table, not a column and not a row in `incident_rejections`.** The two ledgers answer
different questions - *who said no and why* against *who took responsibility* - and a shared table
would carry a nullable reason that means one thing in one row and nothing in the next. Append-only
on migration 0005's pattern for the same reason both the others are: an acknowledgment that could
be edited afterwards cannot answer *who was on the hook at the time*.
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
    CREATE TABLE IF NOT EXISTS incident_acknowledgements (
        id           TEXT PRIMARY KEY,
        at           TIMESTAMPTZ NOT NULL,
        incident_id  TEXT NOT NULL,
        caller       TEXT NOT NULL,
        note         TEXT NOT NULL DEFAULT ''
    );

    CREATE INDEX IF NOT EXISTS incident_acknowledgements_incident_idx
        ON incident_acknowledgements (incident_id, at);

    CREATE OR REPLACE FUNCTION incident_acknowledgements_is_append_only() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION
            'incident_acknowledgements is append-only: % is not permitted (T6.3)', TG_OP
            USING ERRCODE = 'insufficient_privilege';
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS incident_acknowledgements_no_update ON incident_acknowledgements;
    CREATE TRIGGER incident_acknowledgements_no_update
        BEFORE UPDATE OR DELETE ON incident_acknowledgements
        FOR EACH ROW EXECUTE FUNCTION incident_acknowledgements_is_append_only();
    """
    )


def downgrade() -> None:
    op.execute(
        """
    DROP TRIGGER IF EXISTS incident_acknowledgements_no_update ON incident_acknowledgements;
    DROP FUNCTION IF EXISTS incident_acknowledgements_is_append_only();
    DROP TABLE IF EXISTS incident_acknowledgements;
    """
    )
