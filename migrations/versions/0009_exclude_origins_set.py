"""The retrieval exclusion becomes a set (T6.5, piece 3).

Revision ID: 0009
Revises: 0008

`trajectory_retrievals.exclude_origin TEXT` becomes `exclude_origins TEXT[]`.

**Why the column has to move and not just the signature.** T6.5's learning-effect measurement
puts two arms on one corpus: the WITH arm excludes the scenario's own documents, the WITHOUT arm
excludes those *and every other dev scenario in its fault class*. The registration chose that
shape over seeding and unseeding precisely so that **what each arm could see is in the record
rather than in an operator's memory** (§4). A scalar column would record one origin out of four
and make the record say something false about the run - which is worse than recording nothing.

## The conversion is lossless, and it is a retype rather than a rewrite

    NULL              ->  NULL
    'scenario:cart-…' ->  ARRAY['scenario:cart-…']

Every recorded row keeps exactly the fact it recorded: *this retrieval excluded nothing*, or
*this retrieval excluded that one origin*. No row gains or loses an exclusion, and no number
computed from these rows changes - `classify_retrievals` reads *excluded something / excluded
nothing*, and both sides of that are preserved.

**`downgrade` is lossy and says so.** It takes element one and drops the rest, because a `TEXT`
column cannot hold four origins. A database that has recorded a WITHOUT-arm run cannot be
downgraded without losing what that run excluded; there is no honest conversion, so the
migration does the only one available rather than pretending.

## The older ADRs still say `exclude_origin`, and they are left alone

ADR-0008, ADR-0020 and ADR-0022 name the singular column. They are records of what was decided
when they were written and are not edited; ADR-0018 owns the retrieval signature and carries the
addendum that records this widening.
"""

from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
    ALTER TABLE trajectory_retrievals
        ALTER COLUMN exclude_origin TYPE TEXT[]
        USING (CASE WHEN exclude_origin IS NULL THEN NULL ELSE ARRAY[exclude_origin] END);

    ALTER TABLE trajectory_retrievals RENAME COLUMN exclude_origin TO exclude_origins;
    """
    )


def downgrade() -> None:
    op.execute(
        """
    ALTER TABLE trajectory_retrievals RENAME COLUMN exclude_origins TO exclude_origin;

    -- Lossy, deliberately and visibly: a row that excluded four origins comes back carrying
    -- one. See this revision's docstring - there is no honest conversion, and silently keeping
    -- the first is better than a downgrade that cannot run at all only when someone has read
    -- this comment and decided so.
    ALTER TABLE trajectory_retrievals
        ALTER COLUMN exclude_origin TYPE TEXT
        USING (CASE WHEN exclude_origin IS NULL THEN NULL ELSE exclude_origin[1] END);
    """
    )
