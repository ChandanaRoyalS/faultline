"""Deciding whether a firing episode joins an incident or opens one (T2.2, ADR-0016).

This is the question T2.1 refused. ADR-0015 records why: correlation needs the dependency
graph, the state machine and a policy ingest does not hold, and an ingest that guessed would
merge or split incidents silently before anything durable was written.

**The seam is the point.** `TimeOverlapPolicy` ships now and uses time and nothing else.
T2.4 builds the dependency graph and adds `DependencyPolicy` beside it - the orchestrator
does not change.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from faultline.ingest.models import AlertEvent
from faultline.orchestrator.models import Incident, IncidentState, JoinRule


class CorrelationPolicy(Protocol):
    """Does this firing episode belong to any of these incidents?"""

    def match(self, event: AlertEvent, candidates: list[Incident]) -> Incident | None:
        """The incident to join, or `None` to open a new one."""

    @property
    def last_rule(self) -> JoinRule:
        """Which rule decided the most recent `match`. **Read immediately after it.**

        ADR-0017 requires every correlation decision record the rule that made it, and
        deferred persisting it to T4.1. Returning it alongside the incident would change the
        signature every caller and test uses; exposing it as the policy's last answer keeps
        the seam where it was. The orchestrator reads it in the same statement, so there is no
        window in which it can go stale.
        """


class TimeOverlapPolicy:
    """Join the open incident this episode overlaps in time; otherwise open one.

    Time and nothing else - not the service set, not the labels beyond identity, not the
    dependency graph. That is a deliberately weak rule, and what makes it acceptable *here*
    is structural rather than clever: `evalharness.rehearse.require_no_active_faults` refuses
    to inject into a world that already has a fault in it, so the benchmark world never holds
    two concurrent incidents. On the only workload we measure against, time overlap is
    exactly as precise as a graph rule.

    It would mis-merge in production, obviously so - two unrelated faults minutes apart
    become one incident. That is a statement of where this sits, not an argument that it is
    fine (ADR-0016).

    **Never keys on `fingerprint` alone.** Measured across the two captured injections: the
    same four fingerprints appeared in both, forty minutes apart, because the fingerprint is
    a pure function of the alert's labels. Matching on it would merge an incident with every
    previous incident on the same service. Identity here is the episode, which carries
    `startsAt`.

    One consequence worth knowing before relying on it: because *any* live incident wins, at
    most one incident is ever non-terminal under this policy. Everything downstream that
    counts concurrent incidents - the cap, above all - therefore has nothing to count until
    T2.4's `DependencyPolicy` can decline. See `faultline.orchestrator.cap`.
    """

    def __init__(self, settle_window: timedelta) -> None:
        self._settle = settle_window
        self._last_rule = JoinRule.NO_CANDIDATE

    @property
    def last_rule(self) -> JoinRule:
        return self._last_rule

    def match(self, event: AlertEvent, candidates: list[Incident]) -> Incident | None:
        live = [c for c in candidates if not c.is_terminal]
        if live:
            # Most recently active, so a long-quiet incident does not swallow an episode a
            # newer one has a better claim to.
            self._last_rule = JoinRule.TIME_OVERLAP
            return max(live, key=lambda c: c.last_activity_at or datetime.min)

        recently_closed = [c for c in candidates if self._inside_settle_window(c, event)]
        if recently_closed:
            self._last_rule = JoinRule.TIME_OVERLAP_SETTLE
            return max(recently_closed, key=lambda c: c.resolved_at or datetime.min)
        self._last_rule = JoinRule.NO_CANDIDATE
        return None

    def _inside_settle_window(self, incident: Incident, event: AlertEvent) -> bool:
        """A recovery alert arriving just after the last resolution rejoins, not reopens-as-new.

        Measured twice: `emailservice`'s condition crosses the threshold at about the revert
        instant and its alert arrives ~2m30s later, because `ServiceHighErrorRate` carries
        `for: 2m`. In both captures it arrived while other alerts were still firing and
        joined by the clause above. This clause is for the same event arriving a little
        later - timing, not kind.
        """
        if incident.state is not IncidentState.RESOLVED or incident.resolved_at is None:
            return False
        return event.received_at - incident.resolved_at <= self._settle
