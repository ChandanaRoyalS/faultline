"""`/metrics` for the API: the platform's state, read from Postgres on every scrape (T6.6, piece 3).

## Why the numbers come from the database and not from counters in memory

`faultline-investigate` is a subprocess that exits when its investigation does. A histogram
living in it would be scraped never; a counter incremented in it would die with it. **The
long-lived process is the API and the source of truth is Postgres**, so every metric here is
computed from rows at scrape time:

- queue depth and in-flight are `IncidentStore.queued()` and `active_count()` - the exact
  numbers T2.2's admission reads to decide whether an incident waits, exported rather than
  thrown away. A gauge that mirrors state cannot drift from it.
- investigation count, duration, tokens and cost come from `trajectories` and
  `trajectory_steps`, which are append-only, so the counters are monotonic the way Prometheus
  expects and the histogram's cumulative buckets never go down.

The cost is one round of small queries per scrape - a handful of counts and one aggregate over
steps - which at a 15-second interval is nothing a database that holds 600 runs notices.

## What is not here, and why

**Eval scores.** The plan names them. They live in run manifests under `evals/runs/` and in the
eval database, neither of which the API reads, and a Prometheus gauge holding *the last score* is
a dashboard ornament rather than a measurement of anything (`docs/design/t6.6-self-observability.md`
§6). The eval database is the record.

## The no-op contract, again

`prometheus_client` is behind the `observability` extra. `snapshot()` is plain Python and always
works - it is what the tests exercise. `mount()` imports the client lazily and returns `False`
when it is absent, so an API without the extra serves everything else and has no `/metrics`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from faultline.pgread import reading

NAMESPACE = "faultline"

DURATION_BUCKETS_SECONDS = (30.0, 60.0, 120.0, 180.0, 240.0, 300.0, 420.0, 600.0, 900.0)
"""Where the histogram's edges sit. Chosen from what the archive shows: the T6.5 runs took 12-16
minutes end to end including the settle, and the investigation itself 3-5 (the first trace was 4m
21s), so the interesting region is two to ten minutes. Under thirty seconds is a failure."""


class QueueReader(Protocol):
    """The two counters the orchestrator already computes."""

    def queued(self) -> list[Any]: ...
    def active_count(self) -> int: ...


@dataclass(slots=True)
class Snapshot:
    """One scrape's worth of numbers. **Plain data, no client types**, so it can be tested and
    read without the extra installed."""

    queued: int = 0
    active: int = 0
    investigations_by_outcome: dict[str, int] = field(default_factory=dict)
    duration_bucket_counts: list[int] = field(default_factory=list)
    """Cumulative counts per `DURATION_BUCKETS_SECONDS` edge, plus the +Inf bucket last."""
    duration_sum_seconds: float = 0.0
    duration_count: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    usd: float = 0.0
    redactions: int = 0
    """Secret-shaped spans scrubbed out of briefings before they left the process, over every
    recorded completion step (T6.8, `security.scrub`)."""


def snapshot(queue: QueueReader, connection: Any, *, usd_per_mtok: tuple[float, float]) -> Snapshot:
    """Read everything `/metrics` reports. One function, so the dashboard and a test read the
    same numbers the same way."""
    snap = Snapshot(queued=len(queue.queued()), active=queue.active_count())
    # `reading`, not a bare cursor: the first version held its transaction open for the life of
    # the process and blocked migration 0010 on the deployment for 46 minutes (`faultline.pgread`).
    with reading(connection) as cur:
        cur.execute("SELECT COALESCE(outcome, 'running'), count(*) FROM trajectories GROUP BY 1")
        snap.investigations_by_outcome = {str(k): int(v) for k, v in cur.fetchall()}

        # Durations of finished investigations, bucketed in SQL so the row count coming back is
        # the number of edges rather than the number of trajectories.
        edges = list(DURATION_BUCKETS_SECONDS)
        cur.execute(
            "SELECT "
            + ", ".join(
                f"count(*) FILTER (WHERE EXTRACT(EPOCH FROM ended_at - started_at) <= {edge})"
                for edge in edges
            )
            + ", count(*), COALESCE(SUM(EXTRACT(EPOCH FROM ended_at - started_at)), 0) "
            "FROM trajectories WHERE ended_at IS NOT NULL"
        )
        row = cur.fetchone() or [0] * (len(edges) + 2)
        snap.duration_bucket_counts = [int(v) for v in row[: len(edges)]] + [int(row[len(edges)])]
        snap.duration_count = int(row[len(edges)])
        snap.duration_sum_seconds = float(row[len(edges) + 1])

        cur.execute(
            "SELECT COALESCE(SUM(tokens_in), 0), COALESCE(SUM(tokens_out), 0) FROM trajectory_steps"
        )
        tokens_in, tokens_out = cur.fetchone() or (0, 0)
        snap.tokens_in, snap.tokens_out = int(tokens_in), int(tokens_out)
        cur.execute(
            "SELECT COALESCE(SUM((payload->>'redactions')::int), 0) FROM trajectory_steps "
            "WHERE payload ? 'redactions'"
        )
        snap.redactions = int((cur.fetchone() or (0,))[0])
    usd_in, usd_out = usd_per_mtok
    snap.usd = snap.tokens_in / 1e6 * usd_in + snap.tokens_out / 1e6 * usd_out
    return snap


def mount(
    app: Any,
    queue: QueueReader,
    connection: Any,
    *,
    usd_per_mtok: tuple[float, float],
    lockouts: Callable[[], int] | None = None,
) -> bool:
    """Add `GET /metrics` to a FastAPI app if the client is installed. Returns whether it did.

    A custom collector rather than module-level `Gauge()` objects, because the numbers are
    *read* at scrape time rather than *kept* between scrapes - there is nothing to increment.
    `lockouts` (T6.8) is the one exception: the credential limiter's count lives in the web
    process and nowhere else, so it is read from there, through a callable so this module still
    imports without the API.
    """
    try:
        from prometheus_client import (
            CONTENT_TYPE_LATEST,
            CollectorRegistry,
            generate_latest,
        )
        from prometheus_client.core import (
            CounterMetricFamily,
            GaugeMetricFamily,
            HistogramMetricFamily,
        )
    except ImportError:
        return False

    from fastapi import Response

    class _Collector:
        def collect(self) -> Any:
            snap = snapshot(queue, connection, usd_per_mtok=usd_per_mtok)
            yield GaugeMetricFamily(
                f"{NAMESPACE}_incidents_queued",
                "Incidents waiting for T2.2's concurrency cap to admit them.",
                value=snap.queued,
            )
            yield GaugeMetricFamily(
                f"{NAMESPACE}_investigations_active",
                "Investigations in flight, as the orchestrator's admission counts them.",
                value=snap.active,
            )
            by_outcome = CounterMetricFamily(
                f"{NAMESPACE}_investigations",
                "Trajectories recorded, by outcome.",
                labels=["outcome"],
            )
            for outcome, n in sorted(snap.investigations_by_outcome.items()):
                by_outcome.add_metric([outcome], n)
            yield by_outcome
            buckets = [
                (str(edge), float(n))
                for edge, n in zip(
                    DURATION_BUCKETS_SECONDS, snap.duration_bucket_counts, strict=False
                )
            ] + [
                (
                    "+Inf",
                    float(snap.duration_bucket_counts[-1] if snap.duration_bucket_counts else 0),
                )
            ]
            yield HistogramMetricFamily(
                f"{NAMESPACE}_investigation_seconds",
                "Wall time of finished investigations, started_at to ended_at.",
                buckets=buckets,
                sum_value=snap.duration_sum_seconds,
            )
            tokens = CounterMetricFamily(
                f"{NAMESPACE}_model_tokens",
                "Model tokens across every recorded trajectory step.",
                labels=["direction"],
            )
            tokens.add_metric(["in"], snap.tokens_in)
            tokens.add_metric(["out"], snap.tokens_out)
            yield tokens
            yield CounterMetricFamily(
                f"{NAMESPACE}_model_usd",
                "Model spend across every recorded trajectory step, at the runtime's price table.",
                value=snap.usd,
            )
            yield CounterMetricFamily(
                f"{NAMESPACE}_briefing_redactions",
                "Secret-shaped spans scrubbed out of briefings before a model saw them.",
                value=float(snap.redactions),
            )
            if lockouts is not None:
                yield CounterMetricFamily(
                    f"{NAMESPACE}_credential_lockouts",
                    "Clients answered 429 for too many failed credentials, since process start.",
                    value=float(lockouts()),
                )

    registry = CollectorRegistry()
    registry.register(_Collector())

    def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    # `add_api_route` rather than the decorator, because `app` is typed `Any` here - this module
    # must import without FastAPI for the tests that read `snapshot` alone.
    app.add_api_route("/metrics", metrics, methods=["GET"], include_in_schema=False)
    return True
