"""Turning webhook deliveries into deduplicated alert-episode transitions (T2.1).

The whole of ingest's judgement lives here, and there is deliberately very little of it.
Ingest answers one question - *has this exact transition already been published?* - and
declines the more interesting one, *does this alert belong to an incident we already have?*
That second question is correlation, it needs state and policy ingest does not hold, and it
is T2.2's (ADR-0015).

Measured behaviour this is written against: `docs/evidence/t2.1-webhook/README.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from faultline.ingest.dedupe import EpisodeLog
from faultline.ingest.models import Alert, AlertEvent, WebhookPayload
from faultline.ingest.stream import EventStream
from injector.world import canonical_service


@dataclass(frozen=True, slots=True)
class IngestResult:
    """What one delivery did. Returned to Alertmanager, and useful in a log line."""

    received: int = 0
    published: int = 0
    duplicates: int = 0
    stream_ids: tuple[str, ...] = field(default_factory=tuple)


class Receiver:
    """Validates, deduplicates and publishes. Holds no incident state of its own."""

    def __init__(self, episodes: EpisodeLog, stream: EventStream) -> None:
        self._episodes = episodes
        self._stream = stream

    def receive(self, payload: WebhookPayload, received_at: datetime | None = None) -> IngestResult:
        """Publish every alert-episode transition in this delivery that is new.

        Iterates `payload.alerts` rather than reaching for `alerts[0]`: one alert per POST
        is our `group_by`'s doing and not the protocol's, so a config change must not
        silently drop the rest of a group.
        """
        stamp = received_at or datetime.now(UTC)
        published: list[str] = []
        duplicates = 0

        for alert in payload.alerts:
            if not self._episodes.first_sight(alert.delivery_key):
                # A repeat notification or a retry. Already published; say nothing twice.
                duplicates += 1
                continue
            published.append(self._stream.publish(self.to_event(alert, payload, stamp)))

        return IngestResult(
            received=len(payload.alerts),
            published=len(published),
            duplicates=duplicates,
            stream_ids=tuple(published),
        )

    @staticmethod
    def to_event(alert: Alert, payload: WebhookPayload, received_at: datetime) -> AlertEvent:
        """The stream event. `alert` is carried whole, under Alertmanager's field names.

        A `resolved` transition is published exactly like a `firing` one, including when
        ingest never saw the episode open - after a restart, or if the receiver was down
        for the firing notification. Dropping it would be ingest deciding the episode does
        not matter, which is the correlation call it does not make.
        """
        return AlertEvent(
            received_at=received_at,
            fingerprint=alert.fingerprint,
            episode_key=alert.episode_key,
            status=alert.status,
            service=(None if alert.service_name is None else canonical_service(alert.service_name)),
            starts_at=alert.starts_at,
            ends_at=alert.ends_at,
            alert=alert.model_dump(mode="json", by_alias=True),
            group_key=payload.group_key,
        )
