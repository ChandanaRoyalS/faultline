"""Publishing alert-episode transitions onto the Redis stream (T2.1, ADR-0001).

One `XADD` per event, the whole event as JSON under a single `event` field. Streams take
flat field-value maps, and an event with nested objects in it - the alert as delivered -
does not have a flat shape. Splitting it across fields would invent a second encoding of
the same thing, and a consumer would have to reassemble it to get back what ingest already
had. One field, one document, one `model_validate_json` at the other end.
"""

from __future__ import annotations

from typing import Protocol

import redis

from faultline.ingest.models import AlertEvent


class EventStream(Protocol):
    """Where transitions go. The seam the tests substitute at - no Redis in `make check`."""

    def publish(self, event: AlertEvent) -> str:
        """Append one event and return its stream id."""


class RedisEventStream:
    def __init__(self, client: redis.Redis, stream: str) -> None:
        self._client = client
        self._stream = stream

    def publish(self, event: AlertEvent) -> str:
        entry_id = self._client.xadd(self._stream, {"event": event.model_dump_json()})
        return str(entry_id)


class RecordingEventStream:
    """Keeps published events in a list. For tests, and for reading in a REPL."""

    def __init__(self) -> None:
        self.events: list[AlertEvent] = []

    def publish(self, event: AlertEvent) -> str:
        self.events.append(event)
        return f"in-memory-{len(self.events)}"
