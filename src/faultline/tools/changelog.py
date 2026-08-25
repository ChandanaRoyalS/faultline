"""Reading and writing change records (T2.6, ADR-0019).

Two stores behind one Protocol: Postgres for the real thing, a list for tests. The writer is
the injector (`injector.changelog`), the reader is `Tools.change_history`, and neither knows
about the other beyond this module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from faultline.tools.changes import SCHEMA, ChangeRecord


class ChangeLog(Protocol):
    """What the change tool reads and the injector writes."""

    def append(self, record: ChangeRecord) -> None: ...

    def records_for(self, service: str, start: datetime, end: datetime) -> list[ChangeRecord]:
        """Changes on one service inside a window, oldest first.

        An empty list means **observed and empty**. A store that cannot answer must raise, so
        the tool reports an error rather than a negative - five of the nine rehearsed
        investigations rest on that distinction (ADR-0019).
        """


class InMemoryChangeLog:
    """A list. For tests, and for a dry run."""

    def __init__(self) -> None:
        self.records: list[ChangeRecord] = []

    def append(self, record: ChangeRecord) -> None:
        self.records.append(record)

    def records_for(self, service: str, start: datetime, end: datetime) -> list[ChangeRecord]:
        return sorted(
            (r for r in self.records if r.service == service and start <= r.at <= end),
            key=lambda r: r.at,
        )


class PostgresChangeLog:
    """The `change_records` table in the platform Postgres, beside incidents."""

    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def create_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(SCHEMA)
        self._conn.commit()

    def append(self, record: ChangeRecord) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO change_records (id, service, at, actor, resource, action, "
                "summary, before, after) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (id) DO NOTHING",
                (
                    record.id,
                    record.service,
                    record.at,
                    record.actor,
                    record.resource.value,
                    record.action.value,
                    record.summary,
                    record.before,
                    record.after,
                ),
            )
        self._conn.commit()

    def records_for(self, service: str, start: datetime, end: datetime) -> list[ChangeRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, service, at, actor, resource, action, summary, before, after "
                "FROM change_records WHERE service = %s AND at BETWEEN %s AND %s ORDER BY at",
                (service, start, end),
            )
            rows = cur.fetchall()
        return [
            ChangeRecord(
                id=row[0],
                service=row[1],
                at=row[2],
                actor=row[3],
                resource=row[4],
                action=row[5],
                summary=row[6],
                before=row[7],
                after=row[8],
            )
            for row in rows
        ]
