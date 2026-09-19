"""T6.7 piece 3 (a): a worker is killed - really killed, `SIGKILL`, a process - between reading a
stream entry and acking it, and another worker claims the entry and applies it exactly once.

`tests/test_orchestrator.py`'s worker-death tests run against a fake and say so; `tests/
test_integration_consumer.py` proves real Redis has the semantics the fake assumes; neither has
ever ended a process. This file does, against a real Redis, with the real `RedisEventSource` and
the real `ConsumerLoop`, and the two shapes the failure table's row 6 turns on:

* **killed before applying**: the entry is pending against the dead consumer; after the idle
  threshold the survivor's `XAUTOCLAIM` takes it, applies it once, acks it;
* **killed after the write, before the ack**: the dead worker's write is durable (a file stands in
  for Postgres); the survivor claims the entry, its store says *already applied*, and it acks
  without a second write - the write-then-ack rule doing what it is for.

The child is a separate interpreter (`subprocess`), not a thread: a thread cannot be `SIGKILL`ed,
and a thread that dies leaves its connection's pending entries exactly where a killed process
does only by accident of the fake. The kill is `os.kill(pid, SIGKILL)` - no cleanup handler, no
`finally`, nothing the worker could do on the way out.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import redis
from testcontainers.community.redis import RedisContainer

from faultline.ingest.models import AlertEvent, AlertStatus
from faultline.orchestrator.consumer import ConsumerLoop, RedisEventSource
from faultline.orchestrator.core import Applied

pytestmark = pytest.mark.integration

STREAM = "faultline:alerts"
GROUP = "orchestrator"
DEAD = "faultline:alerts:dead"
IDLE_MS = 300
"""How long an entry must sit pending before a survivor may claim it. Small, so the test is
quick; the deployment's `claim_idle_seconds = 60` is the same knob."""


@pytest.fixture(scope="module")
def url() -> Iterator[str]:
    with RedisContainer() as container:
        yield f"redis://{container.get_container_host_ip()}:{container.get_exposed_port(6379)}/0"


def _event() -> AlertEvent:
    now = datetime.now(UTC)
    return AlertEvent(
        received_at=now,
        fingerprint="fp-kill-test",
        episode_key="fp-kill-test@firing",
        status=AlertStatus.FIRING,
        service="cartservice",
        starts_at=now,
        ends_at=None,
        alert={"labels": {"alertname": "ServiceHighErrorRate", "service_name": "cartservice"}},
        group_key='{}:{alertname="ServiceHighErrorRate"}',
    )


@pytest.fixture
def stream(url: str) -> Iterator[redis.Redis]:
    conn: redis.Redis = redis.from_url(url)
    conn.flushall()
    conn.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    conn.xadd(STREAM, {"event": _event().model_dump_json()})
    yield conn
    conn.close()


WORKER = """
import json, sys, time
from pathlib import Path
from faultline.orchestrator.consumer import RedisEventSource

url, consumer, marker, ledger, mode, stream, group, idle_ms, dead = sys.argv[1:10]
source = RedisEventSource.connect(url, stream=stream, group=group, consumer=consumer,
                                  idle_ms=int(idle_ms), dead_letter_stream=dead, block_ms=1000)
entries = source.read(count=32, block=True)
assert entries, "the worker read nothing"
if mode == "after-write":
    # The state change is durable before the ack - the write-then-ack rule. A file is Postgres.
    Path(ledger).write_text(json.dumps([e.episode_key for _, e in entries]))
Path(marker).write_text("read")   # tell the parent we hold the entry
time.sleep(60)                     # "applying" - and the parent kills us here
"""


def _spawn_and_kill(url: str, tmp_path: Path, mode: str) -> int:
    """Start a worker that reads the entry and holds it; kill it with SIGKILL once it has."""
    marker, ledger = tmp_path / "marker", tmp_path / "ledger.json"
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            WORKER,
            url,
            "orchestrator-dead",
            str(marker),
            str(ledger),
            mode,
            STREAM,
            GROUP,
            str(IDLE_MS),
            DEAD,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 30
    while not marker.exists():
        if child.poll() is not None:
            raise AssertionError(f"worker exited early: {child.stderr.read().decode()}")  # type: ignore[union-attr]
        assert time.monotonic() < deadline, "worker never read the entry"
        time.sleep(0.05)
    os.kill(child.pid, signal.SIGKILL)
    child.wait(timeout=10)
    assert child.returncode == -signal.SIGKILL, child.returncode
    return child.pid


class RecordingOrchestrator:
    """The survivor's orchestrator. `applied` is its Postgres; the ledger file is the dead
    worker's, which a real deployment would share through one database."""

    def __init__(self, ledger: Path) -> None:
        self._ledger = ledger
        self.applied: list[str] = []

    def apply(self, event: AlertEvent) -> Applied:
        already: list[str] = json.loads(self._ledger.read_text()) if self._ledger.exists() else []
        if event.episode_key in already:
            return Applied(duplicate=True)
        self.applied.append(event.episode_key)
        return Applied(incident_id="inc-1", opened=True)


def _survivor(url: str, ledger: Path) -> tuple[ConsumerLoop, RecordingOrchestrator]:
    source = RedisEventSource.connect(
        url,
        stream=STREAM,
        group=GROUP,
        consumer="orchestrator-survivor",
        idle_ms=IDLE_MS,
        dead_letter_stream=DEAD,
        block_ms=1000,
    )
    orchestrator = RecordingOrchestrator(ledger)
    return ConsumerLoop(source, orchestrator), orchestrator  # type: ignore[arg-type]


def _pending(conn: redis.Redis) -> list[dict[str, Any]]:
    return list(conn.xpending_range(STREAM, GROUP, min="-", max="+", count=32))  # type: ignore[arg-type]


def test_a_worker_killed_before_applying_leaves_the_entry_for_a_survivor_to_apply_once(
    url: str, stream: redis.Redis, tmp_path: Path
) -> None:
    pid = _spawn_and_kill(url, tmp_path, mode="before-apply")
    assert not (tmp_path / "ledger.json").exists(), "the dead worker wrote nothing"
    pending = _pending(stream)
    assert len(pending) == 1 and pending[0]["consumer"] == b"orchestrator-dead", (
        f"after SIGKILL of pid {pid} the entry is still pending against the dead consumer"
    )

    loop, orchestrator = _survivor(url, tmp_path / "ledger.json")
    too_early = loop.run_once(block=False)
    assert too_early == [] and orchestrator.applied == [], (
        "inside the idle threshold nothing is claimable - a live worker keeps its entries"
    )

    time.sleep(IDLE_MS / 1000 + 0.2)
    applied = loop.run_once(block=False)

    assert [a.opened for a in applied] == [True]
    assert orchestrator.applied == ["fp-kill-test@firing"]
    assert _pending(stream) == [], "claimed, applied, acked"
    assert loop.run_once(block=False) == [], "exactly once: a second pass finds nothing"


def test_a_worker_killed_after_the_write_and_before_the_ack_does_not_duplicate(
    url: str, stream: redis.Redis, tmp_path: Path
) -> None:
    """The row-6 shape the write-then-ack rule exists for. The dead worker's write is durable;
    the entry is still pending; the survivor must claim it, see it applied, and ack it without
    writing twice."""
    _spawn_and_kill(url, tmp_path, mode="after-write")
    assert json.loads((tmp_path / "ledger.json").read_text()) == ["fp-kill-test@firing"]
    assert len(_pending(stream)) == 1

    loop, orchestrator = _survivor(url, tmp_path / "ledger.json")
    time.sleep(IDLE_MS / 1000 + 0.2)
    applied = loop.run_once(block=False)

    assert [a.duplicate for a in applied] == [True]
    assert orchestrator.applied == [], "the survivor wrote nothing - the dead worker already had"
    assert _pending(stream) == [], "and acked what the dead worker could not"
