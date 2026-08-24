"""Event consumption, the eleven-state incident machine, agent fan-out (T2.2-T2.3, T3.5).

Designed in ADR-0016, against the eight real events in `docs/evidence/t2.1-live-smoke/`.
Consumes the alert-episode transitions T2.1 publishes (ADR-0015), correlates them into
incidents, and runs the machine - with the states that depend on T3.x and on the action plane
present, named, and deliberately not designed.
"""

from faultline.orchestrator.cap import InvestigationCap
from faultline.orchestrator.consumer import ConsumerLoop, EventSource
from faultline.orchestrator.core import Applied, Orchestrator
from faultline.orchestrator.correlation import CorrelationPolicy, TimeOverlapPolicy
from faultline.orchestrator.models import Episode, Incident, IncidentState, Severity
from faultline.orchestrator.store import IncidentStore

__all__ = [
    "Applied",
    "ConsumerLoop",
    "CorrelationPolicy",
    "Episode",
    "EventSource",
    "Incident",
    "IncidentState",
    "IncidentStore",
    "InvestigationCap",
    "Orchestrator",
    "Severity",
    "TimeOverlapPolicy",
]
