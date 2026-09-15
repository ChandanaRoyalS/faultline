"""The postmortem accept gate's ledger: who accepted which words (T6.5, piece 2).

`evals/runs/PREREGISTRATION-T6.5.md` §3 decided the gate is **a person, through the approval
surface** - ADR-0039's shape reused rather than re-invented - and named the failure mode so it
could be checked for:

> *a boolean nobody sets.* If the only caller that ever accepts a postmortem is a script, the
> gate is a field and not a gate, and the plan's *"draft for human edit, never auto-published"*
> is unimplemented while appearing done.

## What is recorded, and why it is a digest rather than a name

**The row pins the prose, not the document.** `body_digest` is `corpus.body_digest_of` over the
chunk triples the postmortem produces, which is the same digest the corpus freeze and the drift
check use. Accepting is therefore accepting *these words*: edit a section afterwards and the
seeder finds no accepted row for what is now on disk, and refuses.

An acceptance keyed on `scenario_id` alone would be the boolean §3 warns about wearing a
timestamp. A person would accept a draft, someone would edit it, and the corpus would take the
edit on the strength of a row about a document that no longer exists.

**The digest deliberately excludes front matter.** It is computed from title and sections, so
`origin`, `split` and `incident_id` can be corrected without invalidating a human's reading of
the prose - and the prose is what was read. `parse_postmortem` is what guards the front matter,
structurally, every time.

## What this ledger cannot do

**It cannot make the caller a person.** It records the username the credential proved, and an
automation with the credential produces rows exactly as a person does. What the ledger buys is
that the question is *answerable*: `callers()` returns the distinct names, so "the only caller
is a script" is a query rather than a suspicion. Nothing here enforces an answer, and nothing
here should be read as claiming to.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from faultline.context.corpus import body_digest_of

if TYPE_CHECKING:
    from faultline.context.postmortem import Postmortem

NOTE_LIMIT = 500


def digest_of(postmortem: Postmortem) -> str:
    """The digest a row pins, over the chunk triples the postmortem would seed.

    **Not `hash(file bytes)`**, which would move when someone fixed a typo in `incident_id`, and
    not a hash of the rendered markdown, which would move on a blank line. What a person read is
    the title and the sections, so that is what is hashed - through the same function the corpus
    freeze uses, because a second digest of the same content is how a drift check learns to
    drift (Q45).
    """
    document_id = postmortem.document_id
    rows = [(document_id, section, text) for section, text in postmortem.sections]
    return body_digest_of([(document_id, "title", postmortem.title), *rows])


@dataclass(slots=True)
class Acceptance:
    """One row. A person said these words may join the corpus."""

    scenario_id: str
    body_digest: str
    caller: str
    """The authenticated username, from `auth.guard()`. Never a request-body field: an audit row
    that says *who accepted* is the point of the row (`api/approvals.py`'s own rule)."""

    note: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "at": self.at.isoformat(),
            "scenario_id": self.scenario_id,
            "body_digest": self.body_digest,
            "caller": self.caller,
            "note": self.note,
        }


class AcceptanceStore(Protocol):
    def append(self, acceptance: Acceptance) -> None: ...

    def accepted(self, scenario_id: str, body_digest: str) -> Acceptance | None:
        """The row that admits exactly these words, or `None`. **What the seeder asks.**

        Both arguments, always. Asking by `scenario_id` alone is the question that makes the
        gate a boolean, and asking by digest alone would admit a postmortem accepted for a
        different scenario.
        """
        ...

    def callers(self) -> list[str]:
        """Distinct callers, so §3's failure mode is a query rather than a suspicion."""
        ...


class InMemoryAcceptanceStore:
    def __init__(self) -> None:
        self._rows: list[Acceptance] = []

    def append(self, acceptance: Acceptance) -> None:
        self._rows.append(acceptance)

    def accepted(self, scenario_id: str, body_digest: str) -> Acceptance | None:
        for row in self._rows:
            if row.scenario_id == scenario_id and row.body_digest == body_digest:
                return row
        return None

    def callers(self) -> list[str]:
        return sorted({row.caller for row in self._rows})


class PostgresAcceptanceStore:
    """`postmortem_acceptances`. INSERT and SELECT only; the trigger holds the rest."""

    COLUMNS = "id, at, scenario_id, body_digest, caller, note"

    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def append(self, acceptance: Acceptance) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO postmortem_acceptances ({self.COLUMNS}) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    acceptance.id,
                    acceptance.at,
                    acceptance.scenario_id,
                    acceptance.body_digest,
                    acceptance.caller,
                    acceptance.note[:NOTE_LIMIT],
                ),
            )
        self._conn.commit()

    def accepted(self, scenario_id: str, body_digest: str) -> Acceptance | None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {self.COLUMNS} FROM postmortem_acceptances "
                "WHERE scenario_id = %s AND body_digest = %s ORDER BY at LIMIT 1",
                (scenario_id, body_digest),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return Acceptance(
                id=row[0],
                at=row[1],
                scenario_id=row[2],
                body_digest=row[3],
                caller=row[4],
                note=row[5],
            )

    def callers(self) -> list[str]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT DISTINCT caller FROM postmortem_acceptances ORDER BY caller")
            return [str(row[0]) for row in cur.fetchall()]
