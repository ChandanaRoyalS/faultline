"""Incident persistence (T2.2, ADR-0016). Postgres in production, a dict in tests.

The schema is deliberately the minimum that answers T4.1's question - *which incident got
which alerts, and when* - plus the idempotency table the consumer needs. Everything an
investigation produces (findings, the RCA, proposals) belongs to T3.x and is not invented
here.

`make check` never reaches Postgres: the orchestrator takes an `IncidentStore`, and the
tests pass the in-memory one. Same discipline as ingest's `EpisodeLog` and `EventStream`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from faultline.orchestrator.models import Episode, Incident, IncidentState, Severity

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id                       TEXT PRIMARY KEY,
    state                    TEXT        NOT NULL,
    severity                 TEXT        NOT NULL,
    opened_at                TIMESTAMPTZ NOT NULL,
    last_activity_at         TIMESTAMPTZ NOT NULL,
    resolved_at              TIMESTAMPTZ,
    resolution               TEXT,
    state_before_resolution  TEXT
);

CREATE TABLE IF NOT EXISTS incident_episodes (
    incident_id   TEXT        NOT NULL REFERENCES incidents(id),
    episode_key   TEXT        NOT NULL,
    fingerprint   TEXT        NOT NULL,
    service       TEXT,
    severity      TEXT        NOT NULL,
    alertname     TEXT,
    starts_at     TIMESTAMPTZ NOT NULL,
    ends_at       TIMESTAMPTZ,
    attached_at   TIMESTAMPTZ NOT NULL,
    resolved_at   TIMESTAMPTZ,
    PRIMARY KEY (incident_id, episode_key)
);

-- Stream redelivery, not Alertmanager repeats. Ingest already suppresses the latter
-- (ADR-0015); this suppresses an event published once and delivered twice, and it keys on
-- the same identity so nothing new had to be invented for it.
CREATE TABLE IF NOT EXISTS applied_events (
    episode_key TEXT        NOT NULL,
    status      TEXT        NOT NULL,
    incident_id TEXT        NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (episode_key, status)
);

CREATE INDEX IF NOT EXISTS incidents_state_idx ON incidents (state);
CREATE INDEX IF NOT EXISTS incidents_resolved_at_idx ON incidents (resolved_at);
"""


class IncidentStore(Protocol):
    """What the orchestrator needs to be durable. The seam the tests substitute at."""

    def already_applied(self, episode_key: str, status: str) -> bool: ...

    def mark_applied(
        self, episode_key: str, status: str, incident_id: str, applied_at: datetime
    ) -> None: ...

    def save(self, incident: Incident) -> None:
        """Upsert the incident and its episodes. Called before the stream ack, never after."""

    def get(self, incident_id: str) -> Incident | None: ...

    def correlation_candidates(self, resolved_since: datetime) -> list[Incident]:
        """Every non-terminal incident, plus any resolved at or after `resolved_since`."""

    def queued(self) -> list[Incident]: ...

    def active_count(self) -> int:
        """How many incidents hold a slot against the cap."""


class InMemoryIncidentStore:
    """A dict. For tests, and for reading in a REPL - it loses everything on exit."""

    def __init__(self) -> None:
        self.incidents: dict[str, Incident] = {}
        self.applied: dict[tuple[str, str], str] = {}

    def already_applied(self, episode_key: str, status: str) -> bool:
        return (episode_key, status) in self.applied

    def mark_applied(
        self, episode_key: str, status: str, incident_id: str, applied_at: datetime
    ) -> None:
        self.applied[(episode_key, status)] = incident_id

    def save(self, incident: Incident) -> None:
        self.incidents[incident.id] = incident

    def get(self, incident_id: str) -> Incident | None:
        return self.incidents.get(incident_id)

    def correlation_candidates(self, resolved_since: datetime) -> list[Incident]:
        return [i for i in self.incidents.values() if self._is_candidate(i, resolved_since)]

    @staticmethod
    def _is_candidate(incident: Incident, resolved_since: datetime) -> bool:
        if not incident.is_terminal:
            return True
        closed_at = incident.resolved_at or datetime.min
        return incident.state is IncidentState.RESOLVED and closed_at >= resolved_since

    def queued(self) -> list[Incident]:
        return [i for i in self.incidents.values() if i.state is IncidentState.QUEUED]

    def active_count(self) -> int:
        return sum(1 for i in self.incidents.values() if i.holds_a_slot)


class PostgresIncidentStore:
    """The real one. Not exercised by `make check` - the tests use the in-memory store.

    Every write here happens before the stream ack, never after (ADR-0016): Redis and
    Postgres share no transaction, so the choice is which failure to prefer, and a
    redelivered event that was already applied is a no-op while a lost one is not.
    """

    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def create_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(SCHEMA)
        self._conn.commit()

    def already_applied(self, episode_key: str, status: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM applied_events WHERE episode_key = %s AND status = %s",
                (episode_key, status),
            )
            return cur.fetchone() is not None

    def mark_applied(
        self, episode_key: str, status: str, incident_id: str, applied_at: datetime
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO applied_events (episode_key, status, incident_id, applied_at) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (episode_key, status, incident_id, applied_at),
            )
        self._conn.commit()

    def save(self, incident: Incident) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO incidents (id, state, severity, opened_at, last_activity_at, "
                "resolved_at, resolution, state_before_resolution) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET state = EXCLUDED.state, "
                "severity = EXCLUDED.severity, last_activity_at = EXCLUDED.last_activity_at, "
                "resolved_at = EXCLUDED.resolved_at, resolution = EXCLUDED.resolution, "
                "state_before_resolution = EXCLUDED.state_before_resolution",
                (
                    incident.id,
                    incident.state.value,
                    incident.severity.value,
                    incident.opened_at,
                    incident.last_activity_at,
                    incident.resolved_at,
                    incident.resolution,
                    None
                    if incident.state_before_resolution is None
                    else incident.state_before_resolution.value,
                ),
            )
            for episode in incident.episodes.values():
                cur.execute(
                    "INSERT INTO incident_episodes (incident_id, episode_key, fingerprint, "
                    "service, severity, alertname, starts_at, ends_at, attached_at, "
                    "resolved_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (incident_id, episode_key) DO UPDATE SET "
                    "ends_at = EXCLUDED.ends_at, resolved_at = EXCLUDED.resolved_at",
                    (
                        incident.id,
                        episode.episode_key,
                        episode.fingerprint,
                        episode.service,
                        episode.severity.value,
                        episode.alertname,
                        episode.starts_at,
                        episode.ends_at,
                        episode.attached_at,
                        episode.resolved_at,
                    ),
                )
        self._conn.commit()

    def get(self, incident_id: str) -> Incident | None:
        found = self._load("WHERE id = %s", (incident_id,))
        return found[0] if found else None

    def correlation_candidates(self, resolved_since: datetime) -> list[Incident]:
        return self._load(
            "WHERE state NOT IN ('resolved', 'failed') OR (state = 'resolved' "
            "AND resolved_at >= %s)",
            (resolved_since,),
        )

    def queued(self) -> list[Incident]:
        return self._load("WHERE state = 'queued'", ())

    def active_count(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM incidents WHERE state IN "
                "('triaging', 'planning', 'investigating', 'synthesizing', 'proposing', "
                "'awaiting_approval', 'executing')"
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def _load(self, where: str, params: tuple[Any, ...]) -> list[Incident]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, state, opened_at, last_activity_at, resolved_at, resolution, "
                f"state_before_resolution FROM incidents {where}",
                params,
            )
            rows = cur.fetchall()
            incidents = [
                Incident(
                    id=row[0],
                    state=IncidentState(row[1]),
                    opened_at=row[2],
                    last_activity_at=row[3],
                    resolved_at=row[4],
                    resolution=row[5],
                    state_before_resolution=None if row[6] is None else IncidentState(row[6]),
                )
                for row in rows
            ]
            for incident in incidents:
                cur.execute(
                    "SELECT episode_key, fingerprint, service, severity, alertname, "
                    "starts_at, ends_at, attached_at, resolved_at FROM incident_episodes "
                    "WHERE incident_id = %s",
                    (incident.id,),
                )
                for e in cur.fetchall():
                    incident.episodes[e[0]] = Episode(
                        episode_key=e[0],
                        fingerprint=e[1],
                        service=e[2],
                        severity=Severity(e[3]),
                        alertname=e[4],
                        starts_at=e[5],
                        ends_at=e[6],
                        attached_at=e[7],
                        resolved_at=e[8],
                    )
        return incidents
