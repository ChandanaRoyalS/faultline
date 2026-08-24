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

**The socket has to outlive the block, and this is why that invariant is enforced rather
than commented.** Found in the first live smoke: the consumer drained the backlog correctly,
then died on its first *empty* read with `redis.exceptions.TimeoutError` out of the socket
parser. A blocking `XREADGROUP` waits server-side for `block_ms` and returns nothing; the
client's socket timeout expired first and tore the connection down mid-command. redis-py
8.1.0 defaults `socket_timeout` to **5 seconds** and this module's `block_ms` defaults to
**5000** - the same instant, so the race was not close, it was certain.

It survived every test and a full backlog run because **a non-empty read returns
immediately**. The failure exists only when there is nothing to read, which is the steady
state of a healthy system and a state no fixture-driven test reaches naturally: a replay
source always has an event to hand back. So the invariant is checked at construction, where
it can be tested without an empty stream, and the two numbers that have to agree are no
longer settable independently - `RedisEventSource` owns `block_ms` and sizes its own socket.
"""

from __future__ import annotations

from typing import Any, Protocol

import redis

from faultline.ingest.models import AlertEvent
from faultline.orchestrator.core import Applied, Orchestrator

SOCKET_TIMEOUT_MARGIN_SECONDS = 5.0
"""How much longer than a blocking read the socket must be willing to wait.

Covers the round trip and any scheduling delay between the server deciding to return an
empty result and the client seeing it. Wide, because the cost of being wrong is a crash and
the cost of being generous is a few seconds on a socket that is idle anyway.
"""


def socket_timeout_for(block_ms: int) -> float:
    """The smallest socket timeout that lets a `block_ms` read finish empty-handed."""
    return block_ms / 1000.0 + SOCKET_TIMEOUT_MARGIN_SECONDS


def configured_socket_timeout(client: redis.Redis) -> float | None:
    """What this client will actually wait for a reply, or `None` for forever.

    redis-py records the configured value under `orig_socket_timeout` and only sets
    `socket_timeout` when one was passed explicitly, so both are consulted. That is a detail
    of the client library rather than of its API, which is why the check that uses it is a
    test rather than an assumption.
    """
    kwargs = client.connection_pool.connection_kwargs
    if "socket_timeout" in kwargs:
        value = kwargs["socket_timeout"]
    else:
        value = kwargs.get("orig_socket_timeout")
    return None if value is None else float(value)


class SocketTimeoutError(RuntimeError):
    """A client that will give up before its own blocking read can return."""


class EventSource(Protocol):
    """The stream, as the loop needs it. The seam the tests substitute at."""

    def read(self, count: int, block: bool) -> list[tuple[str, AlertEvent]]:
        """New entries for this consumer, as (entry id, event).

        `block` is whether to wait, not how long: how long is the source's own business,
        because it is the same number the source's socket timeout is derived from.
        """

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
        block_ms: int,
    ) -> None:
        require_socket_outlives_block(client, block_ms)
        self.client = client
        self.block_ms = block_ms
        self._stream = stream
        self._group = group
        self._consumer = consumer
        self._idle_ms = idle_ms
        self._dead_letter = dead_letter_stream

    @classmethod
    def connect(
        cls,
        url: str,
        *,
        stream: str,
        group: str,
        consumer: str,
        idle_ms: int,
        dead_letter_stream: str,
        block_ms: int,
    ) -> RedisEventSource:
        """Build the client and the source together, so the two numbers cannot drift apart.

        This is the only construction path the CLI uses. Passing a hand-built client to
        `__init__` still works - the check runs either way - but then the caller owns getting
        the socket timeout right, and the smoke showed that the default does not.
        """
        return cls(
            redis.from_url(url, socket_timeout=socket_timeout_for(block_ms)),
            stream=stream,
            group=group,
            consumer=consumer,
            idle_ms=idle_ms,
            dead_letter_stream=dead_letter_stream,
            block_ms=block_ms,
        )

    def ensure_group(self) -> None:
        """Create the group if it does not exist. `mkstream` so order of startup is free."""
        try:
            self.client.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def read(self, count: int, block: bool) -> list[tuple[str, AlertEvent]]:
        """`block=False` sends no `BLOCK` at all.

        Not `BLOCK 0`: redis-py passes a zero through, and `XREADGROUP BLOCK 0` blocks
        *forever*, so the one-shot path would hang on an empty stream rather than return.
        """
        response: Any = self.client.xreadgroup(
            self._group,
            self._consumer,
            {self._stream: ">"},
            count=count,
            block=self.block_ms if block else None,
        )
        return _decode(response[0][1]) if response else []

    def claim_stale(self, count: int) -> list[tuple[str, AlertEvent]]:
        response: Any = self.client.xautoclaim(
            self._stream, self._group, self._consumer, min_idle_time=self._idle_ms, count=count
        )
        return _decode(response[1]) if response else []

    def ack(self, entry_id: str) -> None:
        self.client.xack(self._stream, self._group, entry_id)

    def dead_letter(self, entry_id: str, event: AlertEvent, deliveries: int) -> None:
        """Park it and ack it, so a poison event stops cycling forever.

        The threshold is a placeholder (ADR-0016) - there is no measurement behind it, and
        there will not be one until T4.1 has run the loop enough times to produce one.
        """
        self.client.xadd(
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

    def read(self, count: int, block: bool) -> list[tuple[str, AlertEvent]]:
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

    def run_once(self, block: bool = False) -> list[Applied]:
        """One pass: claim anything stranded, then take new entries. Returns what happened."""
        results: list[Applied] = []
        for entry_id, event in [
            *self._source.claim_stale(self._batch),
            *self._source.read(self._batch, block),
        ]:
            results.append(self._orchestrator.apply(event))
            self._source.ack(entry_id)
        return results

    def run_forever(self) -> None:  # pragma: no cover - a loop
        while True:
            self.run_once(block=True)


def require_socket_outlives_block(client: redis.Redis, block_ms: int) -> None:
    """Raise unless this client will wait longer for a reply than its own read blocks for.

    The regression this exists to stop is one line of configuration: redis-py's default
    5-second `socket_timeout` against this module's default 5000ms block. See the module
    docstring for how that failed and why no fixture reproduces it.

    A `socket_timeout` of `None` passes deliberately: it means wait forever, which cannot
    lose this race. It is a legitimate choice for a dedicated consumer connection - the cost
    is that a silently dropped connection is noticed only when the server would have replied,
    rather than at the timeout, and recovery is then whatever the caller's reconnect does.
    `connect()` does not choose it; a caller building its own client may.
    """
    timeout = configured_socket_timeout(client)
    if timeout is None:
        return
    if timeout <= block_ms / 1000.0:
        raise SocketTimeoutError(
            f"socket_timeout is {timeout}s but a blocking read waits {block_ms / 1000.0}s, "
            "so the socket gives up before the server answers and the first read that finds "
            "nothing kills the consumer. This only ever fails on an empty stream, which is "
            f"the healthy steady state. Use at least {socket_timeout_for(block_ms)}s "
            "(RedisEventSource.connect does), or pass socket_timeout=None deliberately."
        )
