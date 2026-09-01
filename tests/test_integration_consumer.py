"""The consumer-group semantics the kill-a-worker test assumes (T2.2, T2.3).

`tests/test_orchestrator.py`'s worker-death tests run against `GroupStream`, a fake, and say
so: they prove the loop survives a worker death *given* these semantics, not that Redis
provides them. This is the other half. Four properties, against a real server, using the same
three commands `RedisEventSource` issues - `XREADGROUP`, `XAUTOCLAIM`, `XACK`.

If any of these fails, the fake is wrong and every conclusion drawn from it is void. That is
the point of writing them: a fake nobody has checked is an assumption with a test's costume on.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import redis
from testcontainers.community.redis import RedisContainer

pytestmark = pytest.mark.integration

STREAM = "faultline:alerts"
GROUP = "orchestrator"
A, B = "orchestrator-1", "orchestrator-2"


@pytest.fixture(scope="module")
def url() -> Iterator[str]:
    with RedisContainer() as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest.fixture
def client(url: str) -> Iterator[redis.Redis]:
    conn: redis.Redis = redis.from_url(url)
    conn.flushall()
    conn.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    conn.xadd(STREAM, {"event": "{}"})
    yield conn
    conn.close()


def pending_for(conn: redis.Redis, consumer: str) -> list[Any]:
    entries: Any = conn.xpending_range(STREAM, GROUP, min="-", max="+", count=32)
    return [e for e in entries if e["consumer"].decode() == consumer]


def read_as(conn: redis.Redis, consumer: str) -> list[Any]:
    response: Any = conn.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=32)
    return response[0][1] if response else []


def test_an_entry_a_consumer_reads_is_pending_against_that_consumer(
    client: redis.Redis,
) -> None:
    """`GroupStream.read` moves the entry into the reader's pending list. So does Redis."""
    assert read_as(client, A)

    assert len(pending_for(client, A)) == 1
    assert pending_for(client, B) == []


def test_acking_clears_the_pending_entry(client: redis.Redis) -> None:
    """`GroupMember.ack` pops it. So does `XACK`."""
    entry_id = read_as(client, A)[0][0]

    client.xack(STREAM, GROUP, entry_id)

    assert pending_for(client, A) == []


def test_an_idle_consumers_entry_can_be_claimed_by_another(client: redis.Redis) -> None:
    """The kill-a-worker case. A holds it, A dies, B claims it - and it moves."""
    read_as(client, A)

    claimed: Any = client.xautoclaim(STREAM, GROUP, B, min_idle_time=0, count=32)

    assert claimed[1], "B claimed nothing from a dead A"
    assert pending_for(client, A) == []
    assert len(pending_for(client, B)) == 1


def test_a_fresh_entry_is_not_claimable(client: redis.Redis) -> None:
    """`min_idle_time` is the entire safety argument, and it is Redis's to enforce.

    `GroupStream` models this as a `dead_consumers` set, which is a coarser thing: the fake
    says *who* is dead, Redis says *how long* an entry has gone unacked. The fake is safe
    because it never claims from a live consumer; this asserts the real mechanism behind
    that, so nobody later concludes that claiming is unconditional.
    """
    read_as(client, A)

    claimed: Any = client.xautoclaim(STREAM, GROUP, B, min_idle_time=60_000, count=32)

    assert claimed[1] == [], "an entry read moments ago must not be claimable"
    assert len(pending_for(client, A)) == 1
