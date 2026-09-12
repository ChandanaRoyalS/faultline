"""Who took the critical incident (T6.3, the sev-1 ack gate).

The plan's deliverable names a *"sev-1 ack gate"* and nothing in the tree had any notion of
acknowledgment at all. `evals/runs/PREREGISTRATION-T6.3.md` §2.5 registers what it is for: a
`critical` incident cannot be **approved from the surface** until somebody has said, in the
ledger, that they are the one watching it.

**The gate is on the button, not on the executor**, and the asymmetry is deliberate. A token minted
at a terminal by `faultline-approve` still works on a critical incident, because that is an
operator's own hand and the gate exists to stop a click made by somebody who has not looked. An
executor that enforced it would be refusing a human who had already decided, in a process that
cannot ask them anything.

One row per acknowledgment, append-only, and **the first one is the gate**: a second is recorded
and changes nothing, because two people taking the same incident is a fact worth keeping and not
an error worth raising.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

NOTE_LIMIT = 500


@dataclass(slots=True)
class Acknowledgement:
    incident_id: str
    caller: str
    note: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "at": self.at.isoformat(),
            "incident_id": self.incident_id,
            "caller": self.caller,
            "note": self.note,
        }


class AcknowledgementStore(Protocol):
    def append(self, acknowledgement: Acknowledgement) -> None: ...

    def first(self, incident_id: str) -> Acknowledgement | None:
        """The acknowledgment that opened the gate, or `None` while it is shut."""
        ...


class InMemoryAcknowledgementStore:
    def __init__(self) -> None:
        self._rows: list[Acknowledgement] = []

    def append(self, acknowledgement: Acknowledgement) -> None:
        self._rows.append(acknowledgement)

    def first(self, incident_id: str) -> Acknowledgement | None:
        for row in self._rows:
            if row.incident_id == incident_id:
                return row
        return None


class PostgresAcknowledgementStore:
    """`incident_acknowledgements`. INSERT and SELECT only; the trigger holds the rest."""

    COLUMNS = "id, at, incident_id, caller, note"

    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def append(self, acknowledgement: Acknowledgement) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO incident_acknowledgements ({self.COLUMNS}) "
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    acknowledgement.id,
                    acknowledgement.at,
                    acknowledgement.incident_id,
                    acknowledgement.caller,
                    acknowledgement.note[:NOTE_LIMIT],
                ),
            )
        self._conn.commit()

    def first(self, incident_id: str) -> Acknowledgement | None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {self.COLUMNS} FROM incident_acknowledgements "
                "WHERE incident_id = %s ORDER BY at LIMIT 1",
                (incident_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return Acknowledgement(
                id=row[0], at=row[1], incident_id=row[2], caller=row[3], note=row[4]
            )
