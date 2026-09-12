"""The rejection ledger: why a human said no, and how many times (T6.3).

**A rejection is evidence, not a flag.** T2.3 wrote *"`REJECTED` exits to targeted
re-investigation, reason required"* in Phase 2 and nothing has been able to honour the second half
since, because there was nowhere to put a reason. This module is that place, and
`evals/runs/PREREGISTRATION-T6.3.md` §2.2 registers three properties of it before the build:

- **A row per rejection**, never a column that keeps only the latest. The second rejection of an
  incident is the interesting one - it says the re-investigation did not help - and a column would
  overwrite the first.
- **Append-only at the database** (migration 0006), on the action ledger's pattern. The reason is
  what an operator told a machine before it spent money on their behalf.
- **The count is the cap.** `count()` is what decides whether a rejected incident is
  re-investigated again, so the ledger is load-bearing rather than decorative.

The reason text is **operator input and untrusted** in exactly the sense telemetry is
(`THREAT-MODEL.md` thesis 1): it reaches the proposer in a user message, quoted and capped, and
never the system prompt - which is what keeps `stamp.prompt_digest()` still.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

REASON_LIMIT = 2000
"""Longer than any reason a person types and short enough that the briefing's essential section
cannot be crowded out by one. A reason at the limit is truncated with a marker rather than
refused: losing the tail of a long explanation is better than losing the rejection."""

TRUNCATED = " […truncated]"


def clean_reason(reason: str) -> str:
    """The reason as it will be stored. Raises on nothing usable.

    Whitespace-only is not a reason, and the machine will not move an incident without one
    (`machine.record_rejection`). This is the one place that decides what *empty* means, so the
    route, the CLI and the machine cannot disagree about it.
    """
    text = reason.strip()
    if not text:
        raise ValueError("a rejection needs a reason: nothing but whitespace was given")
    if len(text) > REASON_LIMIT:
        return text[: REASON_LIMIT - len(TRUNCATED)] + TRUNCATED
    return text


@dataclass(slots=True)
class Rejection:
    incident_id: str
    reason: str
    caller: str
    proposal_id: str = ""
    action_id: str = ""
    target: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "at": self.at.isoformat(),
            "incident_id": self.incident_id,
            "proposal_id": self.proposal_id,
            "action_id": self.action_id,
            "target": self.target,
            "reason": self.reason,
            "caller": self.caller,
        }


class RejectionStore(Protocol):
    def append(self, rejection: Rejection) -> None: ...

    def for_incident(self, incident_id: str) -> list[Rejection]:
        """Oldest first."""
        ...

    def latest(self, incident_id: str) -> Rejection | None:
        """What the re-investigation is told. The most recent rejection and no others: an
        agent given three contradictory reasons is being asked to satisfy a committee."""
        ...

    def count(self, incident_id: str) -> int:
        """The cap reads this."""
        ...


class InMemoryRejectionStore:
    """The tests' double. Append-only by having no other method."""

    def __init__(self) -> None:
        self._rows: list[Rejection] = []

    def append(self, rejection: Rejection) -> None:
        self._rows.append(rejection)

    def for_incident(self, incident_id: str) -> list[Rejection]:
        return [r for r in self._rows if r.incident_id == incident_id]

    def latest(self, incident_id: str) -> Rejection | None:
        found = self.for_incident(incident_id)
        return found[-1] if found else None

    def count(self, incident_id: str) -> int:
        return len(self.for_incident(incident_id))


class PostgresRejectionStore:
    """`incident_rejections`. INSERT and SELECT are the only statements here, and the table's
    trigger is what makes that a property rather than a habit."""

    COLUMNS = "id, at, incident_id, proposal_id, action_id, target, reason, caller"

    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def append(self, rejection: Rejection) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO incident_rejections ({self.COLUMNS}) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    rejection.id,
                    rejection.at,
                    rejection.incident_id,
                    rejection.proposal_id,
                    rejection.action_id,
                    rejection.target,
                    rejection.reason,
                    rejection.caller,
                ),
            )
        self._conn.commit()

    def for_incident(self, incident_id: str) -> list[Rejection]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {self.COLUMNS} FROM incident_rejections "
                "WHERE incident_id = %s ORDER BY at",
                (incident_id,),
            )
            return [self._row(row) for row in cur.fetchall()]

    def latest(self, incident_id: str) -> Rejection | None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {self.COLUMNS} FROM incident_rejections "
                "WHERE incident_id = %s ORDER BY at DESC LIMIT 1",
                (incident_id,),
            )
            row = cur.fetchone()
            return self._row(row) if row else None

    def count(self, incident_id: str) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM incident_rejections WHERE incident_id = %s",
                (incident_id,),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0

    @staticmethod
    def _row(row: Any) -> Rejection:
        return Rejection(
            id=row[0],
            at=row[1],
            incident_id=row[2],
            proposal_id=row[3],
            action_id=row[4],
            target=row[5],
            reason=row[6],
            caller=row[7],
        )
