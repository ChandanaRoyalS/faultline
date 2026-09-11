"""The action plane's ledger (T6.2).

Revision ID: 0005
Revises: 0004

`action_audit` is one row per attempt to act on the world - approved, refused, executed, error,
kill switch - and **no row is ever changed**. The plan's word is *"append-only audit"*, and
`evals/runs/PREREGISTRATION-T6.2.md` §2.5 says how that is held: at the database, not in code. A
trigger raises on `UPDATE` and on `DELETE`, whoever the caller is and whatever role they hold, so
the property survives a connection that has every privilege the application role has - which is
the connection the executor itself uses. `tests/test_integration_executor.py` tries both and
expects the refusal.

Why a trigger and not `REVOKE`: the application role owns the table, and an owner's privileges
can be granted back by the owner. A trigger fires regardless. The rows read by
`faultline.executor.audit.PostgresAuditStore` are exactly the columns here.
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
    CREATE TABLE IF NOT EXISTS action_audit (
        id             TEXT PRIMARY KEY,
        at             TIMESTAMPTZ NOT NULL,
        incident_id    TEXT NOT NULL DEFAULT '',
        proposal_id    TEXT NOT NULL DEFAULT '',
        action_id      TEXT NOT NULL DEFAULT '',
        target         TEXT NOT NULL DEFAULT '',
        -- The token's id, never the token: a bearer credential has no place in a ledger.
        token_id       TEXT,
        caller         TEXT NOT NULL,
        outcome        TEXT NOT NULL,
        reason         TEXT NOT NULL DEFAULT '',
        command        JSONB NOT NULL DEFAULT '[]'::jsonb,
        exit_code      INT,
        output_sha256  TEXT,
        inverse        TEXT NOT NULL DEFAULT '',
        drift          JSONB NOT NULL DEFAULT '{}'::jsonb
    );

    CREATE INDEX IF NOT EXISTS action_audit_incident_idx ON action_audit (incident_id, at);
    -- Single use: "has this token id been spent" is one indexed lookup.
    CREATE INDEX IF NOT EXISTS action_audit_token_idx ON action_audit (token_id);

    CREATE OR REPLACE FUNCTION action_audit_is_append_only() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'action_audit is append-only: % is not permitted (T6.2)', TG_OP
            USING ERRCODE = 'insufficient_privilege';
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS action_audit_no_update ON action_audit;
    CREATE TRIGGER action_audit_no_update
        BEFORE UPDATE OR DELETE ON action_audit
        FOR EACH ROW EXECUTE FUNCTION action_audit_is_append_only();
    """
    )


def downgrade() -> None:
    op.execute(
        """
    DROP TRIGGER IF EXISTS action_audit_no_update ON action_audit;
    DROP FUNCTION IF EXISTS action_audit_is_append_only();
    DROP TABLE IF EXISTS action_audit;
    """
    )
