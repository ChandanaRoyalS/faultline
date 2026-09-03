"""The count that says whether the exclusion filter fired (T4.1b).

Revision ID: 0003
Revises: 0002

T4.1b asks for two things this repository had only half of: *"the count of filtered artifacts is
logged per run, and a scored run where the filter did not fire is marked invalid, not merely
annotated - silent non-enforcement is how this defect returns."*

`trajectory_retrievals.exclude_origin` has recorded, since T4.1b's first half, that an exclusion
was **asked for**. It cannot record that the exclusion **had something to exclude**, and those
are different facts: the filter is SQL - `AND origin <> %(origin)s` - so a query whose exclusion
matches nothing returns exactly what a query with no exclusion returns, and the row looks
identical either way.

**Nullable, and the null is meaningful.** Every row written before this migration has no count
and must not be read as zero: `NULL` is *not computed*, `0` is *asked for and matched nothing*.
On a scored dev run the second is a failed leave-one-out - the scenario's own narrative is in the
corpus by construction - and the harness refuses to count such a run rather than annotating it.
Backfilling would require re-deriving a corpus state that no longer exists, so the 60-odd
retrieval rows recorded before today stay `NULL` and stay honest about it.
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE trajectory_retrievals ADD COLUMN IF NOT EXISTS excluded_count integer")


def downgrade() -> None:
    op.execute("ALTER TABLE trajectory_retrievals DROP COLUMN IF EXISTS excluded_count")
