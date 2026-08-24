"""Reading `faultline:alerts` as a consumer group, and acking after the write (T2.2).

ADR-0001 chose Redis Streams with consumer groups, explicit acks and pending-entry claim on
worker death. ADR-0016 fixed the two rules this loop turns on:

**An event is processed when its incident state change is durable - not when the
investigation finishes.** Acking only after a completed investigation would hold entries
pending for minutes, replay work already done on every restart, and couple stream health to
model latency.

**Write, then ack.** Redis and Postgres share no transaction, so the choice is which failure
to prefer. A crash between the write and the ack redelivers an event already applied, which
`Orchestrator.apply` makes a no-op; the reverse order loses it silently.
"""

from __future__ import annotations

from typing import Any, Protocol

import redis

from faultline.ingest.models import AlertEvent
from faultline.orchestrator.core import Applied, Orchestrator


class EventSource(Protocol):
    """The stream, as the loop needs it. The seam the tests substitute at."""

    def read(self, count: int, block_ms: int) -> list[tuple[str, AlertEvent]]:
        """New entries for this consumer, as (entry id, event)."""

    def claim_stale(self, count: int) -> list[tuple[str, AlertEvent]]:
        """Entries another consumer took and never acked. Safe because apply is idempotent."""

    def ack(self, entry_id: str) -> None: ...

    def dead_letter(self, entry_id: str, event: AlertEvent, deliveries: int) -> None:
        """An entry delivered too many times and never acked."""


class RedisEventSource:
    """`XREADGROUP` / `XAUTOCLAIM` / `XACK` on one stream, one group, one consumer name."""

    def __init__(
        self,
        client: redis.Redis,
        stream: str,
        group: str,
        consumer: str,
        idle_ms: int,
        dead_letter_stream: str,
    ) -> None:
        self._client = client
        self._stream = stream
        self._group = group
        self._consumer = consumer
        self._idle_ms = idle_ms
        self._dead_letter = dead_letter_stream

    def ensure_group(self) -> None:
        """Create the group if it does not exist. `mkstream` so order of startup is free."""
        try:
            self._client.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def read(self, count: int, block_ms: int) -> list[tuple[str, AlertEvent]]:
        response: Any = self._client.xreadgroup(
            self._group, self._consumer, {self._stream: ">"}, count=count, block=block_ms
        )
        return _decode(response[0][1]) if response else []

    def claim_stale(self, count: int) -> list[tuple[str, AlertEvent]]:
        response: Any = self._client.xautoclaim(
            self._stream, self._group, self._consumer, min_idle_time=self._idle_ms, count=count
        )
        return _decode(response[1]) if response else []

    def ack(self, entry_id: str) -> None:
        self._client.xack(self._stream, self._group, entry_id)

    def dead_letter(self, entry_id: str, event: AlertEvent, deliveries: int) -> None:
        """Park it and ack it, so a poison event stops cycling forever.

        The threshold is a placeholder (ADR-0016) - there is no measurement behind it, and
        there will not be one until T4.1 has run the loop enough times to produce one.
        """
        self._client.xadd(
            self._dead_letter,
            {"event": event.model_dump_json(), "entry_id": entry_id, "deliveries": deliveries},
        )
        self.ack(entry_id)


def _decode(entries: Any) -> list[tuple[str, AlertEvent]]:
    decoded: list[tuple[str, AlertEvent]] = []
    for entry_id, fields in entries:
        raw = fields[b"event"] if b"event" in fields else fields["event"]
        decoded.append((_text(entry_id), AlertEvent.model_validate_json(raw)))
    return decoded


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


class ReplayEventSource:
    """Hands over a fixed list of events, in order, and records what was acked.

    For tests. It is how the eight captured events are replayed through the real loop rather
    than through `Orchestrator.apply` alone - the loop's own rules (write-then-ack, one ack
    per entry) are worth exercising too.
    """

    def __init__(self, events: list[AlertEvent]) -> None:
        self.pending = [(f"replay-{i}", e) for i, e in enumerate(events)]
        self.acked: list[str] = []
        self.dead_lettered: list[str] = []

    def read(self, count: int, block_ms: int) -> list[tuple[str, AlertEvent]]:
        batch, self.pending = self.pending[:count], self.pending[count:]
        return batch

    def claim_stale(self, count: int) -> list[tuple[str, AlertEvent]]:
        return []

    def ack(self, entry_id: str) -> None:
        self.acked.append(entry_id)

    def dead_letter(self, entry_id: str, event: AlertEvent, deliveries: int) -> None:
        self.dead_lettered.append(entry_id)


class ConsumerLoop:
    """Read a batch, apply each event, ack each one after its state change is durable."""

    def __init__(self, source: EventSource, orchestrator: Orchestrator, batch: int = 32) -> None:
        self._source = source
        self._orchestrator = orchestrator
        self._batch = batch

    def run_once(self, block_ms: int = 0) -> list[Applied]:
        """One pass: claim anything stranded, then take new entries. Returns what happened."""
        results: list[Applied] = []
        for entry_id, event in [
            *self._source.claim_stale(self._batch),
            *self._source.read(self._batch, block_ms),
        ]:
            results.append(self._orchestrator.apply(event))
            self._source.ack(entry_id)
        return results

    def run_forever(self, block_ms: int = 5000) -> None:  # pragma: no cover - a loop
        while True:
            self.run_once(block_ms)
