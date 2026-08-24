"""Alert ingestion: Alertmanager webhook, fingerprinting, dedupe (T2.1).

Ingest's contract is **faithful, deduplicated delivery of alert-episode transitions** onto
the Redis stream, and nothing more. It does not decide whether two alerts belong to one
incident - see ADR-0015, and `docs/evidence/t2.1-webhook/README.md` for the captured
deliveries the design is measured against.
"""

from faultline.ingest.models import EVENT_VERSION, Alert, AlertEvent, AlertStatus, WebhookPayload
from faultline.ingest.receiver import IngestResult, Receiver

__all__ = [
    "EVENT_VERSION",
    "Alert",
    "AlertEvent",
    "AlertStatus",
    "IngestResult",
    "Receiver",
    "WebhookPayload",
]
