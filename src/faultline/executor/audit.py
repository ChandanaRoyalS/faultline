"""The audit: one row per attempt, executed or refused, and nothing can change a row.

**Append-only is enforced at the database, not asserted in code** (`migrations/versions/0005`):
a trigger raises on `UPDATE` or `DELETE`, whoever the caller is, and
`tests/test_integration_executor.py` tries both and expects the refusal. A code-level promise
would hold only for code that keeps it.

**What a row carries.** The proposal it acted on and the token's *id* - never the token, which is
a bearer credential for as long as it is unspent. The caller. The exact argv the executor ran, its
exit code and a hash of its output - the output itself is world state and lands in the evidence
directory, not in the ledger. The refusal reason where there is one. And **the inverse** where one
exists: what would put the world back, recorded at the moment the executor knew it, so that a
re-test of the fault does not have to be reconstructed from memory (the plan: *"every executed
action records its inverse where one exists, enabling one-click revert"*). `restart_service` has no
inverse and the row says so in words rather than with a null.

**Outcomes** are five, and only two of them touched the world: `approved` (a token was minted -
who, for what, expiring when; the token itself is not here), `refused` (the executor did not act,
with a reason), `kill_switch` (a refusal that gets its own name because an operator reading the
ledger for "is the switch working" should not have to parse reasons), `executed` (it acted,
cleanly), and `error` (it tried and the command failed - the world may be half-changed and the
operator is told).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

SPENDING_OUTCOMES = frozenset({"executed", "error"})
"""Outcomes that consume the token. A refusal before the world was touched leaves the approval
standing: a token refused because the kill switch was on is still a valid approval once it is off,
and making the approver re-approve for the executor's own state would be the executor blaming the
human for its configuration."""


@dataclass(slots=True)
class AuditRecord:
    incident_id: str
    proposal_id: str
    action_id: str
    target: str
    token_id: str | None
    caller: str
    outcome: str
    reason: str = ""
    command: list[str] = field(default_factory=list)
    exit_code: int | None = None
    output_sha256: str | None = None
    inverse: str = ""
    drift: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["at"] = self.at.isoformat()
        return row


class AuditStore(Protocol):
    def append(self, record: AuditRecord) -> None: ...

    def spent(self, token_id: str) -> AuditRecord | None:
        """The row that consumed this token, if any - `SPENDING_OUTCOMES` only."""
        ...

    def for_incident(self, incident_id: str) -> list[AuditRecord]: ...


class InMemoryAuditStore:
    """The tests' double. Append-only by having no other method."""

    def __init__(self) -> None:
        self._rows: list[AuditRecord] = []

    def append(self, record: AuditRecord) -> None:
        self._rows.append(record)

    def spent(self, token_id: str) -> AuditRecord | None:
        for row in self._rows:
            if row.token_id == token_id and row.outcome in SPENDING_OUTCOMES:
                return row
        return None

    def for_incident(self, incident_id: str) -> list[AuditRecord]:
        return [r for r in self._rows if r.incident_id == incident_id]

    @property
    def rows(self) -> list[AuditRecord]:
        return list(self._rows)


class PostgresAuditStore:
    """`action_audit`. INSERT and SELECT are the only statements this class contains, and the
    table's trigger is what makes that a property rather than a habit."""

    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def append(self, record: AuditRecord) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO action_audit (id, at, incident_id, proposal_id, action_id, target, "
                "token_id, caller, outcome, reason, command, exit_code, output_sha256, inverse, "
                "drift) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    record.id,
                    record.at,
                    record.incident_id,
                    record.proposal_id,
                    record.action_id,
                    record.target,
                    record.token_id,
                    record.caller,
                    record.outcome,
                    record.reason,
                    json.dumps(record.command),
                    record.exit_code,
                    record.output_sha256,
                    record.inverse,
                    json.dumps(record.drift, sort_keys=True),
                ),
            )
        self._conn.commit()

    def spent(self, token_id: str) -> AuditRecord | None:
        rows = self._select(
            "WHERE token_id = %s AND outcome = ANY(%s)", (token_id, sorted(SPENDING_OUTCOMES))
        )
        return rows[0] if rows else None

    def for_incident(self, incident_id: str) -> list[AuditRecord]:
        return self._select("WHERE incident_id = %s", (incident_id,))

    def _select(self, where: str, params: tuple[Any, ...]) -> list[AuditRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, at, incident_id, proposal_id, action_id, target, token_id, caller, "
                "outcome, reason, command, exit_code, output_sha256, inverse, drift "
                f"FROM action_audit {where} ORDER BY at",
                params,
            )
            rows = cur.fetchall()
        records = []
        for row in rows:
            command = row[10] if isinstance(row[10], list) else json.loads(row[10] or "[]")
            drift = row[14] if isinstance(row[14], dict) else json.loads(row[14] or "{}")
            records.append(
                AuditRecord(
                    id=row[0],
                    at=row[1],
                    incident_id=row[2],
                    proposal_id=row[3],
                    action_id=row[4],
                    target=row[5],
                    token_id=row[6],
                    caller=row[7],
                    outcome=row[8],
                    reason=row[9] or "",
                    command=command,
                    exit_code=row[11],
                    output_sha256=row[12],
                    inverse=row[13] or "",
                    drift=drift,
                )
            )
        return records
