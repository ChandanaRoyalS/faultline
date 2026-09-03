"""The eval database (T4.4).

Revision ID: 0004
Revises: 0003

T4.4: *"Persist every eval run with config fingerprint (prompt versions, model, context
settings); generate a comparative report between any two versions."* Method: *"Eval schema
alongside the platform DB; config captured as a hash of all behavior-relevant settings -
including repeat count R, judge version, and seed policy (T4.6)."*

**Until this migration the eval database was a directory.** 128 `manifest.json` files under
`evals/runs/`, which is a real record and an unqueryable one: "how did configuration A do against
configuration B on the dev split" is a question nobody writes the second `jq` pipeline for, and
T4.4's comparison generator had nothing to read.

## Two tables, and the fingerprint is the join

`eval_configs` is the set of distinct behaviour-relevant configurations ever run. `eval_runs` is
every run, pointing at the configuration it ran under. A comparison is then a `GROUP BY` rather
than a directory walk, and *"a comparative report between any two versions"* is two fingerprints.

**`settings` holds the exact object the fingerprint was taken over**, so a fingerprint is always
reproducible from the row that carries it and never has to be trusted. `missing` names the inputs
that were absent when it was computed - which matters more here than it would in a system built
this way from the start, because the manifests span six generations of the harness and the older
ones carry neither a freeze block nor a budget block. **Two runs share a fingerprint only when the
same inputs were present and equal**, so a run recorded before an input existed cannot silently
collide with one recorded after it.

## Scored, discarded and invalid are all rows

`outcome` is one of `scored`, `discarded`, `paused` or `invalid`. All of them are stored, for the
reason ADR-0022 §3.3 gives for keeping discard directories: *the number of runs is a fact nobody
can hide by tidying*. A table that held only successes would make the discard rate unrecoverable
and would quietly answer "how often does the harness work" with "always".

## The columns are the scored fields; everything else stays in `manifest`

The same rule migration 0002 used for proposals. The lifted columns are what a comparison groups,
filters or averages on; the rest of the manifest is JSONB and is read when a reader already knows
which run they want. A schema that lifted every key would need a migration for every harness
change, which is how eval schemas rot.
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS eval_configs (
            fingerprint     TEXT PRIMARY KEY,
            first_seen      TIMESTAMPTZ NOT NULL,
            runtime_version TEXT,
            settings        JSONB NOT NULL,
            missing         JSONB NOT NULL DEFAULT '[]'::jsonb
        );

        CREATE TABLE IF NOT EXISTS eval_runs (
            run_id               TEXT PRIMARY KEY,
            scenario_id          TEXT NOT NULL,
            split                TEXT,
            scenario_fingerprint TEXT,
            started_at           TIMESTAMPTZ,
            finished_at          TIMESTAMPTZ,

            outcome              TEXT NOT NULL,
            discard_reason       TEXT,
            invalid_reason       TEXT,

            trajectory_id        TEXT,
            runtime_version      TEXT,
            config_fingerprint   TEXT REFERENCES eval_configs(fingerprint),
            world_generation     TEXT,

            -- T4.6's three, nullable because no run before it recorded them. NULL is
            -- "not recorded", never "R = 1": a run that never stated its repeat count has not
            -- claimed to be a single observation, it has claimed nothing.
            repeat_count         INT,
            judge_version        TEXT,
            seed_policy          TEXT,

            cost_usd             DOUBLE PRECISION,
            tokens_in            INT,
            tokens_out           INT,
            latency_ms           INT,

            reached_a_class      BOOLEAN,
            fault_class_truth    TEXT,
            fault_class_returned TEXT,
            fault_class_correct  BOOLEAN,
            fault_class_abstained BOOLEAN,
            fix_class_truth      TEXT,
            fix_class_returned   TEXT,
            fix_class_correct    BOOLEAN,
            fix_class_abstained  BOOLEAN,
            triage_recall        DOUBLE PRECISION,
            triage_precision     DOUBLE PRECISION,

            manifest             JSONB NOT NULL
        );

        CREATE INDEX IF NOT EXISTS eval_runs_scenario_idx ON eval_runs (scenario_id);
        CREATE INDEX IF NOT EXISTS eval_runs_config_idx   ON eval_runs (config_fingerprint);
        CREATE INDEX IF NOT EXISTS eval_runs_split_idx    ON eval_runs (split, outcome);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS eval_runs; DROP TABLE IF EXISTS eval_configs;")
