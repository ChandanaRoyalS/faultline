"""Applying alert-episode transitions to incidents (T2.2, ADR-0016).

The whole of the orchestrator's judgement, over Protocol seams: a `CorrelationPolicy`, an
`IncidentStore`, and a cap. No Redis and no Postgres appear here, which is what lets the
measured case - the eight captured events, replayed in order - run inside `make check`.

**One place where this reads ADR-0016 rather than transcribes it.** The ADR says an incident
closes when every episode is resolved *and the settle window has elapsed*, and separately
that a `RESOLVED` incident *reopens* when a firing correlates into it inside that window.
Those are two routes to the same outcome. This implements the second: the incident goes to
`RESOLVED` on the last resolution - an observable event, no timer - and the settle window
governs reopening. The alternative needs a periodic tick, and makes an incident's closing
time depend on when that tick happens to run rather than on anything the world did.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from faultline.ingest.models import AlertEvent, AlertStatus
from faultline.notify.announce import SILENT, Announcer
from faultline.orchestrator.cap import InvestigationCap
from faultline.orchestrator.correlation import CorrelationPolicy
from faultline.orchestrator.machine import transition
from faultline.orchestrator.models import (
    Episode,
    Incident,
    IncidentState,
    JoinRule,
    Severity,
)
from faultline.orchestrator.store import IncidentStore


@dataclass(frozen=True, slots=True)
class Applied:
    """What one event did. The orchestrator's equivalent of ingest's `IngestResult`."""

    incident_id: str | None = None
    opened: bool = False
    joined: bool = False
    resolved_incident: bool = False
    duplicate: bool = False
    ignored_reason: str | None = None


class Orchestrator:
    """Consumes alert-episode transitions; owns incident state and admission."""

    def __init__(
        self,
        store: IncidentStore,
        policy: CorrelationPolicy,
        cap: InvestigationCap,
        settle_window: timedelta,
        announcer: Announcer = SILENT,
    ) -> None:
        self._store = store
        self._policy = policy
        self._cap = cap
        self._settle = settle_window
        self._announcer = announcer
        """T5.2. Defaults to an announcer that sends nothing, so no existing caller changes and
        no test acquires a network dependency by accident."""

    def apply(self, event: AlertEvent) -> Applied:
        """Apply one event. Idempotent on `(episode_key, status)`.

        That key is the identity ingest already dedupes on (ADR-0015), reused here for a
        different mechanism: ingest suppresses Alertmanager repeats and retries, this
        suppresses stream redelivery of an event published once and delivered twice. Neither
        substitutes for the other.
        """
        if self._store.already_applied(event.episode_key, event.status.value):
            return Applied(duplicate=True)

        if event.status is AlertStatus.FIRING:
            result = self._apply_firing(event)
        else:
            result = self._apply_resolved(event)

        if result.incident_id is not None:
            self._store.mark_applied(
                event.episode_key, event.status.value, result.incident_id, event.received_at
            )
        return result

    # --- firing ---------------------------------------------------------------

    def _apply_firing(self, event: AlertEvent) -> Applied:
        candidates = self._store.correlation_candidates(event.received_at - self._settle)
        target = self._policy.match(event, candidates)
        # Read in the same statement as the match, per `CorrelationPolicy.last_rule`.
        rule = self._policy.last_rule

        if target is None:
            return self._open(event, rule)

        reopened = target.state is IncidentState.RESOLVED
        if reopened:
            self._reopen(target)
        self._attach(target, event, rule)
        self._store.save(target)
        return Applied(incident_id=target.id, joined=True)

    def _open(self, event: AlertEvent, rule: JoinRule) -> Applied:
        incident = Incident(opened_at=event.received_at, last_activity_at=event.received_at)
        self._attach(incident, event, rule)
        self._admit_or_queue(incident)
        self._store.save(incident)
        # **After the durable write, and only here.** Same rule as the consumer's write-then-ack:
        # a notification about an incident that failed to persist is a message about something
        # that does not exist. And only on `_open` - a reopen inside the settle window is the
        # same incident, and a channel that announced it twice would be reporting one fault as
        # two. `apply()` is idempotent on (episode_key, status), so a stream redelivery of the
        # opening event never reaches this line a second time.
        self._announcer.incident_opened(incident)
        return Applied(incident_id=incident.id, opened=True)

    def _attach(self, incident: Incident, event: AlertEvent, rule: JoinRule) -> None:
        """Record the episode on the incident. **Does not change state.**

        ADR-0016: an alert joining an incident already past `OPEN` does not restart triage.
        It is recorded so the specialists and the scribe see the full blast radius, which is
        what T3.1 scores triage on.
        """
        labels = event.alert.get("labels", {})
        incident.episodes.setdefault(
            event.episode_key,
            Episode(
                episode_key=event.episode_key,
                fingerprint=event.fingerprint,
                service=event.service,
                severity=Severity.from_label(labels.get("severity")),
                alertname=labels.get("alertname"),
                starts_at=event.starts_at,
                attached_at=event.received_at,
                join_rule=rule,
            ),
        )
        incident.last_activity_at = event.received_at

    def _reopen(self, incident: Incident) -> None:
        """A firing correlated into a resolved incident inside the settle window."""
        back_to = incident.state_before_resolution or IncidentState.OPEN
        transition(incident, back_to, trigger="a firing episode inside the settle window")
        incident.resolved_at = None
        incident.resolution = None
        incident.state_before_resolution = None
        if back_to is IncidentState.OPEN:
            self._admit_or_queue(incident)

    # --- resolved -------------------------------------------------------------

    def _apply_resolved(self, event: AlertEvent) -> Applied:
        holder = next(
            (
                i
                for i in self._store.correlation_candidates(event.received_at - self._settle)
                if event.episode_key in i.episodes
            ),
            None,
        )
        if holder is None:
            # ADR-0015 publishes these deliberately - a receiver that was down for the
            # firing, or restarted. Inventing an incident to close is worse than dropping a
            # close for one that never opened here.
            return Applied(ignored_reason="no incident holds this episode")

        episode = holder.episodes[event.episode_key]
        episode.resolved_at = event.received_at
        episode.ends_at = event.ends_at
        holder.last_activity_at = event.received_at

        closed = False
        if holder.all_resolved and not holder.is_terminal:
            self._close(holder, resolution=_resolution_for(holder))
            closed = True
        self._store.save(holder)
        return Applied(incident_id=holder.id, resolved_incident=closed)

    def _close(self, incident: Incident, *, resolution: str) -> None:
        """To `RESOLVED`, from wherever it was.

        An investigation in flight is **not** cancelled (ADR-0016): the fault is over, the
        question of what caused it is not, and the eval harness scores exactly that answer.
        The state it was in is remembered so a reopen puts it back.
        """
        was_investigating = incident.holds_a_slot
        incident.state_before_resolution = incident.state
        transition(incident, IncidentState.RESOLVED, trigger="every episode resolved")
        incident.resolved_at = incident.last_activity_at
        incident.resolution = resolution
        if was_investigating:
            self._promote_from_queue()

    # --- the cap --------------------------------------------------------------

    def _admit_or_queue(self, incident: Incident) -> None:
        if self._cap.has_room(self._store.active_count()):
            transition(incident, IncidentState.TRIAGING, trigger="a slot was free")
        else:
            transition(incident, IncidentState.QUEUED, trigger="the cap was full")

    def _promote_from_queue(self) -> None:
        """A slot freed. Admit the highest-severity, then oldest, queued incident."""
        if not self._cap.has_room(self._store.active_count()):
            return
        nxt = self._cap.next_admission(self._store.queued())
        if nxt is None:
            return
        transition(nxt, IncidentState.TRIAGING, trigger="a slot freed")
        self._store.save(nxt)

    def abandon_queued(self, incident: Incident) -> None:
        """Close a queued incident explicitly. Same outcome the resolution path reaches.

        Kept as a named entry point because a future sweeper - one that expires incidents
        stuck in `QUEUED` - is the other way into this state, and it should not have to know
        how `resolution` is spelled.
        """
        self._close(incident, resolution=_resolution_for(incident))
        self._store.save(incident)


def _resolution_for(incident: Incident) -> str:
    """Why an incident ended - and the one case ADR-0016 marks for decision.

    An incident whose alerts all resolve while it is still `OPEN` or `QUEUED` was never
    investigated. **ADR-0016 chose option A, abandon**, on the reasoning that a slot spent on
    a fault that is already over is a slot not spent on one that is still happening, which
    under a cap is the whole point. It is the option that loses data, and the argument for it
    rests on a cap value nobody has measured, so it is marked for decision rather than
    closed.

    Both conditions the ADR attached to that choice apply here:

    - **The outcome is recorded, not silent.** `never_started` is written on the incident, so
      one that vanished because the queue was busy is visible as exactly that.
    - **A scored run must never hit it.** Every scenario's fault is reverted after a 300s
      hold, so under a full queue a scored incident could be abandoned and the run would look
      like a scoring failure rather than a dropped incident. **T4.1 must assert its incident
      was actually investigated and mark the run invalid otherwise** - ADR-0008 makes the
      same argument about filter enforcement: silent non-enforcement is how a defect returns
      after being fixed once.
    """
    never_ran = incident.state in {IncidentState.OPEN, IncidentState.QUEUED}
    return "never_started" if never_ran else "alerts_resolved"
