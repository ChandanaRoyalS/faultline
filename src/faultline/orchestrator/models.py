"""Incident state: the eleven states, severity, and what an incident holds (T2.2 / T3.5).

The states and every transition's trigger are ADR-0016's. This module encodes them and
nothing else - no policy, no persistence, no agent contracts.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class IncidentState(StrEnum):
    """The eleven states `docs/ARCHITECTURE.md` commits to, as ADR-0016 names them.

    Five of them (`TRIAGING` through `PROPOSING`) are entered by agent outcomes T3.x has not
    built, and two (`AWAITING_APPROVAL`, `EXECUTING`) by an action plane that has no task
    number at all - see `docs/PLAN.md`, "Discovered omissions". They exist here because the
    machine has to be able to *be* in them; what advances them is deliberately not decided.
    """

    OPEN = "open"
    QUEUED = "queued"
    TRIAGING = "triaging"
    PLANNING = "planning"
    INVESTIGATING = "investigating"
    SYNTHESIZING = "synthesizing"
    PROPOSING = "proposing"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    RESOLVED = "resolved"
    FAILED = "failed"


TERMINAL = frozenset({IncidentState.RESOLVED, IncidentState.FAILED})

INVESTIGATING_STATES = frozenset(
    {
        IncidentState.TRIAGING,
        IncidentState.PLANNING,
        IncidentState.INVESTIGATING,
        IncidentState.SYNTHESIZING,
        IncidentState.PROPOSING,
        IncidentState.AWAITING_APPROVAL,
        IncidentState.EXECUTING,
    }
)
"""States that hold a slot against the concurrency cap.

`OPEN` and `QUEUED` do not: an incident that has not been admitted is not consuming an
investigation. Approval and execution do, because the incident is still in flight and
releasing its slot would let the cap be exceeded by anything waiting on a human.
"""

AGENT_DRIVEN = frozenset(
    {
        IncidentState.TRIAGING,
        IncidentState.PLANNING,
        IncidentState.INVESTIGATING,
        IncidentState.SYNTHESIZING,
        IncidentState.PROPOSING,
    }
)
"""Advanced by T3.x agent outcomes. Not built - see `machine.record_agent_outcome`."""

ACTION_PLANE_DRIVEN = frozenset({IncidentState.AWAITING_APPROVAL, IncidentState.EXECUTING})
"""Advanced by approval and execution outcomes. Not built, and unnumbered in the plan."""


class Severity(StrEnum):
    """What `alert.labels.severity` carries.

    `compose/prometheus/alert-rules.yml` defines exactly two values: `critical` for
    `ServiceHighErrorRate` and `ServiceNoTraffic`, `warning` for `ServiceHighLatency`. A
    label outside that set sorts as `warning` rather than raising - an unrecognised severity
    is a reason to deprioritise an incident, never a reason to drop it.
    """

    CRITICAL = "critical"
    WARNING = "warning"

    @classmethod
    def from_label(cls, label: str | None) -> Severity:
        return cls.CRITICAL if label == cls.CRITICAL.value else cls.WARNING

    @property
    def rank(self) -> int:
        """Higher sorts first in the overflow queue. See `cap.InvestigationCap`."""
        return 2 if self is Severity.CRITICAL else 1


@dataclass(slots=True)
class Episode:
    """One alert-episode attached to an incident. Mirrors ADR-0015's event fields."""

    episode_key: str
    fingerprint: str
    service: str | None
    severity: Severity
    alertname: str | None
    starts_at: datetime
    attached_at: datetime
    ends_at: datetime | None = None
    resolved_at: datetime | None = None

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None


@dataclass(slots=True)
class Incident:
    """What T4.1 has to be able to ask about later: which alerts, in which incident, when."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: IncidentState = IncidentState.OPEN
    opened_at: datetime | None = None
    last_activity_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution: str | None = None
    """Why it ended. `alerts_resolved`, or `never_started` for the queued-then-resolved case
    ADR-0016 marks for decision - recorded rather than silent, which is the condition that
    decision came with."""

    episodes: dict[str, Episode] = field(default_factory=dict)
    state_before_resolution: IncidentState | None = None
    """Where a reopened incident goes back to. ADR-0016: a `RESOLVED` incident returns to its
    prior state, or to `OPEN` if it never started."""

    @property
    def severity(self) -> Severity:
        """The maximum across the incident's episodes, recomputed as episodes join."""
        return (
            Severity.CRITICAL
            if any(e.severity is Severity.CRITICAL for e in self.episodes.values())
            else Severity.WARNING
        )

    @property
    def all_resolved(self) -> bool:
        return bool(self.episodes) and all(e.is_resolved for e in self.episodes.values())

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL

    @property
    def holds_a_slot(self) -> bool:
        return self.state in INVESTIGATING_STATES
