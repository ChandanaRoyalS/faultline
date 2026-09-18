"""T6.6 piece 3: `/metrics` reads the database on every scrape.

`snapshot()` is plain Python and is what these exercise, against a fake queue and a fake
connection. `mount()` needs `prometheus_client` and is tested only where the extra is present.
"""

from __future__ import annotations

import importlib.util
from typing import Any

import pytest

from faultline.observability import metrics
from faultline.observability.metrics import DURATION_BUCKETS_SECONDS, snapshot

HAS_CLIENT = importlib.util.find_spec("prometheus_client") is not None


class _Queue:
    def __init__(self, queued: int, active: int) -> None:
        self._queued, self._active = queued, active

    def queued(self) -> list[Any]:
        return [object()] * self._queued

    def active_count(self) -> int:
        return self._active


class _Cursor:
    """Answers the three queries `snapshot` makes, in order, from canned rows."""

    def __init__(
        self, outcomes: list[tuple[str, int]], durations: list[float], tokens: tuple[int, int]
    ) -> None:
        self._outcomes = outcomes
        self._durations = durations
        self._tokens = tokens
        self._pending: list[Any] = []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def execute(self, sql: str, *params: Any) -> None:
        if "GROUP BY" in sql:
            self._pending = list(self._outcomes)
        elif "EXTRACT(EPOCH" in sql:
            counts = [
                sum(1 for d in self._durations if d <= edge) for edge in DURATION_BUCKETS_SECONDS
            ]
            self._pending = [(*counts, len(self._durations), float(sum(self._durations)))]
        elif "SUM(tokens_in)" in sql:
            self._pending = [self._tokens]
        else:  # pragma: no cover
            raise AssertionError(f"unexpected query: {sql}")

    def fetchall(self) -> list[Any]:
        return self._pending

    def fetchone(self) -> Any:
        return self._pending[0] if self._pending else None


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _Cursor:
        return self._cursor


def test_the_queue_gauges_are_the_orchestrators_own_counts() -> None:
    """**The point of the metrics, per the plan**: queue depth is *"the metric that makes T2.2's
    concurrency cap observable"*, and it is computed on every admission and thrown away. Read
    from the same two methods the admission reads, so the gauge cannot disagree with the cap."""
    conn = _Connection(_Cursor([], [], (0, 0)))

    snap = snapshot(_Queue(queued=4, active=3), conn, usd_per_mtok=(5.0, 25.0))

    assert snap.queued == 4
    assert snap.active == 3


def test_durations_bucket_cumulatively_with_an_inf_bucket_last() -> None:
    """Prometheus histograms are cumulative: each bucket counts everything at or below its edge,
    and +Inf counts everything. Built in SQL so the rows coming back are edges, not trajectories."""
    conn = _Connection(_Cursor([], durations=[45.0, 90.0, 261.0, 1200.0], tokens=(0, 0)))

    snap = snapshot(_Queue(0, 0), conn, usd_per_mtok=(5.0, 25.0))

    assert len(snap.duration_bucket_counts) == len(DURATION_BUCKETS_SECONDS) + 1
    assert snap.duration_bucket_counts[0] == 0, "nothing under 30s"
    assert snap.duration_bucket_counts[1] == 1, "one under 60s"
    assert snap.duration_bucket_counts[-2] == 3, "three under 900s"
    assert snap.duration_bucket_counts[-1] == 4, "+Inf holds all four"
    assert snap.duration_count == 4
    assert snap.duration_sum_seconds == 1596.0


def test_cost_uses_the_runtimes_own_price_table() -> None:
    """The USD counter and every manifest's `cost_usd` are the same arithmetic, because both
    read `AgentSettings.usd_per_mtok_*`. A metric priced differently from the record would be a
    second opinion about what a run cost."""
    conn = _Connection(_Cursor([("dispatched", 2)], [], tokens=(2_000_000, 100_000)))

    snap = snapshot(_Queue(0, 0), conn, usd_per_mtok=(5.0, 25.0))

    assert snap.tokens_in == 2_000_000 and snap.tokens_out == 100_000
    assert snap.usd == pytest.approx(2 * 5.0 + 0.1 * 25.0)
    assert snap.investigations_by_outcome == {"dispatched": 2}


def test_an_empty_database_snapshots_to_zeros_not_errors() -> None:
    """A fresh deployment has no trajectories. `/metrics` on it is a page of zeros, which is a
    fact about the deployment and not a failure of the endpoint."""
    conn = _Connection(_Cursor([], [], (0, 0)))

    snap = snapshot(_Queue(0, 0), conn, usd_per_mtok=(5.0, 25.0))

    assert snap.duration_count == 0 and snap.usd == 0.0
    assert snap.duration_bucket_counts[-1] == 0


@pytest.mark.skipif(HAS_CLIENT, reason="the client is installed; this covers the absent case")
def test_mount_without_the_client_declines_and_leaves_the_app_alone() -> None:
    """The `agents` pattern once more: no extra, no `/metrics`, no error, everything else served."""

    class App:
        def add_api_route(self, *a: Any, **k: Any) -> None:  # pragma: no cover
            raise AssertionError("must not be reached without the client")

    assert metrics.mount(App(), _Queue(0, 0), None, usd_per_mtok=(5.0, 25.0)) is False


@pytest.mark.skipif(not HAS_CLIENT, reason="needs the observability extra")
def test_mount_serves_the_snapshot_in_exposition_format() -> None:  # pragma: no cover
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    conn = _Connection(_Cursor([("dispatched", 3)], [200.0], tokens=(1000, 50)))
    assert metrics.mount(app, _Queue(queued=2, active=1), conn, usd_per_mtok=(5.0, 25.0)) is True

    body = TestClient(app).get("/metrics").text

    assert "faultline_incidents_queued 2.0" in body
    assert "faultline_investigations_active 1.0" in body
    assert 'faultline_investigations_total{outcome="dispatched"} 3.0' in body
    assert 'faultline_model_tokens_total{direction="in"} 1000.0' in body
    assert "faultline_investigation_seconds_bucket" in body
