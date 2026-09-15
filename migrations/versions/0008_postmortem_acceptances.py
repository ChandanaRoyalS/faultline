"""The postmortem accept gate's ledger (T6.5).

Revision ID: 0008
Revises: 0007

`postmortem_acceptances` is one row per person who read a postmortem's prose and said it may
join the retrieval corpus. `evals/runs/PREREGISTRATION-T6.5.md` §3 says what the gate is for and
names the failure it exists to avoid - *a boolean nobody sets*.

**Keyed on `(scenario_id, body_digest)`, not on `scenario_id`.** A row admits *these words*: the
digest is `corpus.body_digest_of` over the postmortem's title and sections, so editing a section
after acceptance leaves the seeder with no row for what is now on disk. An acceptance keyed on
the scenario alone would be the boolean §3 warns about, wearing a timestamp.

**No unique constraint on that pair, deliberately.** Re-accepting the same words is a fact worth
keeping - two people reading the same draft is what a review looks like - and the seeder asks
whether *any* row admits the digest. This follows migration 0007's rule that the first row is the
gate and a second changes nothing.

Append-only on migration 0005's pattern, for the reason all three ledgers are: an acceptance that
could be edited afterwards cannot answer *who let this into the corpus*.
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
    CREATE TABLE IF NOT EXISTS postmortem_acceptances (
        id           TEXT PRIMARY KEY,
        at           TIMESTAMPTZ NOT NULL,
        scenario_id  TEXT NOT NULL,
        body_digest  TEXT NOT NULL,
        caller       TEXT NOT NULL,
        note         TEXT NOT NULL DEFAULT ''
    );

    CREATE INDEX IF NOT EXISTS postmortem_acceptances_lookup_idx
        ON postmortem_acceptances (scenario_id, body_digest);

    CREATE OR REPLACE FUNCTION postmortem_acceptances_is_append_only() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION
            'postmortem_acceptances is append-only: % is not permitted (T6.5)', TG_OP
            USING ERRCODE = 'insufficient_privilege';
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS postmortem_acceptances_no_update ON postmortem_acceptances;
    CREATE TRIGGER postmortem_acceptances_no_update
        BEFORE UPDATE OR DELETE ON postmortem_acceptances
        FOR EACH ROW EXECUTE FUNCTION postmortem_acceptances_is_append_only();
    """
    )


def downgrade() -> None:
    op.execute(
        """
    DROP TRIGGER IF EXISTS postmortem_acceptances_no_update ON postmortem_acceptances;
    DROP FUNCTION IF EXISTS postmortem_acceptances_is_append_only();
    DROP TABLE IF EXISTS postmortem_acceptances;
    """
    )
