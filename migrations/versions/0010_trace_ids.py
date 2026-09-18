"""Trace and span ids on trajectories and their steps (T6.6, piece 2).

Revision ID: 0010
Revises: 0009

`trajectories.trace_id TEXT NOT NULL DEFAULT ''` and
`trajectory_steps.trace_id TEXT NOT NULL DEFAULT ''`, `trajectory_steps.span_id TEXT NOT NULL
DEFAULT ''`.

**Why columns and not a payload key.** The join from a scored run to its trace in Tempo is the
whole point of T6.6's design (`docs/design/t6.6-self-observability.md` §2): two records of one
event, joinable rather than parallel. A key inside `payload` JSON would be joinable only by a
reader who knew to look, and unindexable. Columns make *"every step of this trace"* a WHERE clause.

**Why empty string and not NULL.** `Trajectory.add` stamps the span in scope on every step, and
with nothing exporting that is two empty strings - *not traced*, legible as emptiness. Every row
written before this revision is in the same state for the same reason, so the default is the
truth about them rather than a placeholder: no run before 2026-09-18 was traced, because nothing
could trace one.

`downgrade` drops the columns. Nothing else reads them, and a trace id is recoverable from Tempo
by incident id for as long as Tempo keeps it, which is the only reader that would care.
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
    ALTER TABLE trajectories      ADD COLUMN IF NOT EXISTS trace_id TEXT NOT NULL DEFAULT '';
    ALTER TABLE trajectory_steps  ADD COLUMN IF NOT EXISTS trace_id TEXT NOT NULL DEFAULT '';
    ALTER TABLE trajectory_steps  ADD COLUMN IF NOT EXISTS span_id  TEXT NOT NULL DEFAULT '';
    CREATE INDEX IF NOT EXISTS trajectory_steps_trace_idx ON trajectory_steps (trace_id)
        WHERE trace_id <> '';
    """
    )


def downgrade() -> None:
    op.execute(
        """
    DROP INDEX IF EXISTS trajectory_steps_trace_idx;
    ALTER TABLE trajectory_steps DROP COLUMN IF EXISTS span_id;
    ALTER TABLE trajectory_steps DROP COLUMN IF EXISTS trace_id;
    ALTER TABLE trajectories     DROP COLUMN IF EXISTS trace_id;
    """
    )
