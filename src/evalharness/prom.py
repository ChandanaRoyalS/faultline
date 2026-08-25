"""Prometheus and Loki access, shared by everything that reads the world (T1.5).

Extracted from evalharness.rehearse when the baseline recorder became a second consumer.
T4.1's scoring harness will be the third, and all three have to ask the same questions the
same way - a baseline measured with one query and a scenario scored with a slightly
different one is not a comparison.

**The transport moved out at T2.6** (ADR-0019). T2.6's tool layer is the fourth consumer and
could not import this module: ADR-0004 keeps benchmark infrastructure out of the product, so
the HTTP client lives in `faultline.telemetry` and both sides import it. The names below are
re-exported so nothing in the harness had to change, and `tests/test_telemetry.py` pins that
the extraction left every capture query's URL byte-identical.

What stayed here is what belongs to the harness: the fixed capture set, and the runtime
query built per target service. An agent composes its own PromQL and has no use for either.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

from faultline.telemetry import (
    HTTP_TIMEOUT,
    LOKI,
    PROMETHEUS,
    QueryError,
    get_json,
    now,
    query_range,
    stamp,
)

__all__ = [
    "HTTP_TIMEOUT",
    "LOKI",
    "METRIC_QUERIES",
    "POLL_SECONDS",
    "PROMETHEUS",
    "RUNTIME_CAPTURE",
    "RUNTIME_FAMILIES",
    "QueryError",
    "alert_intervals",
    "firing_alerts",
    "get_json",
    "now",
    "query_range",
    "runtime_query",
    "series_points",
    "stamp",
]

POLL_SECONDS = 15

# The four series every capture takes. Keys become filenames under metrics/.
METRIC_QUERIES: dict[str, str] = {
    "error-ratio": (
        'sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m]))'
        " / sum by(service_name) (rate(calls_total[2m]))"
    ),
    "call-rate": "sum by(service_name) (rate(calls_total[2m]))",
    "latency-p95": (
        "histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))"
    ),
    "alerts-firing": 'ALERTS{alertstate="firing"}',
}

RUNTIME_CAPTURE = "runtime"
"""Filename stem of the fifth capture. Scenario bundles only - see `runtime_query`."""

RUNTIME_FAMILIES = ("process_runtime_.*", "runtime_.*", "system_memory_.*")
"""The metric families a service reports about its own process, across the demo's runtimes.

`process_runtime_jvm_*`, `runtime_cpython_*`, `process_runtime_go_*`,
`process_runtime_dotnet_*` and `system_memory_*`. Prometheus anchors regexes, so
`runtime_.*` does not also match `process_runtime_*` - all three patterns are needed.
"""


def runtime_query(service: str) -> str:
    """The target service's own runtime metrics, over the incident window.

    Measured on `ad-memory-squeeze` and `recommendation-memory-squeeze`: these series
    **vanish** while the process is being killed faster than it can reach a serving state,
    and that absence is what separates "no traffic because the process is gone" from "no
    traffic because nobody called it" - a distinction `ServiceNoTraffic` cannot make. See
    `evals/scenarios/CATALOG.md`, "Runtime metrics reach Prometheus, and their absence is
    the signal", for the measurements and the boundary conditions.

    **The label is `exported_job`, not `service_name`.** Prometheus renamed the exporter's
    `job` label because it collided with the scrape job's, so every query in
    `METRIC_QUERIES` - all of which key on `service_name`, which the span metrics do carry
    - silently matches nothing here. `service` is the compose service name, which is what
    `exported_job` holds: use `injector.world.canonical_service` to get there from a fault
    target, since a target may name either a container or a service.
    """
    return f'{{exported_job="{service}", __name__=~"{"|".join(RUNTIME_FAMILIES)}"}}'


def firing_alerts() -> list[str]:
    """Alert names currently firing, in the order Prometheus reports them."""
    payload = get_json(PROMETHEUS, "/api/v1/alerts", {})
    data = payload.get("data")
    alerts = data.get("alerts", []) if isinstance(data, dict) else []
    names: list[str] = []
    for alert in alerts:
        if not isinstance(alert, dict) or alert.get("state") != "firing":
            continue
        labels = alert.get("labels", {})
        name = labels.get("alertname") if isinstance(labels, dict) else None
        service = labels.get("service_name") if isinstance(labels, dict) else None
        if isinstance(name, str):
            names.append(f"{name}/{service}" if isinstance(service, str) else name)
    return names


def series_points(payload: dict[str, Any]) -> dict[str, list[tuple[float, float]]]:
    """A query_range payload as {service_name: [(unix_seconds, value), ...]}.

    NaN and +Inf are dropped rather than carried: a ratio over zero traffic is not a
    measurement of anything, and averaging it in would understate every statistic.
    """
    data = payload.get("data")
    results = data.get("result", []) if isinstance(data, dict) else []
    out: dict[str, list[tuple[float, float]]] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        labels = item.get("metric", {})
        name = labels.get("service_name") if isinstance(labels, dict) else None
        if not isinstance(name, str):
            continue
        points: list[tuple[float, float]] = []
        for pair in item.get("values", []):
            if not (isinstance(pair, list) and len(pair) == 2):
                continue
            try:
                value = float(pair[1])
            except (TypeError, ValueError):
                continue
            if value != value or value in (float("inf"), float("-inf")):
                continue
            points.append((float(pair[0]), value))
        if points:
            out.setdefault(name, []).extend(points)
    return out


def alert_intervals(
    payload: dict[str, Any],
    step: int,
    since: datetime | None = None,
    revert: datetime | None = None,
) -> list[dict[str, Any]]:
    """Every firing episode in an ALERTS query_range, with when it started and stopped.

    Derived from a captured series rather than polled, so it costs nothing extra and covers
    the whole window instead of whatever happened to be firing at one instant. A
    point-in-time snapshot systematically misses later waves: an incident that pages on two
    services and grows to ten over six minutes looks five times smaller than it was.

    Two things this has to get right, both found by running it on real captures:

    `since` drops samples from before the fault. A bundle's window opens five minutes early
    to show the healthy baseline, and if the previous rehearsal is still clearing, its
    alerts sit in that pre-roll - attributing them to this incident inflates the blast
    radius with someone else's fault.

    Episodes are split rather than collapsed to min/max. An alert that stops and restarts
    is two episodes, and reporting the span between them as continuous firing hides exactly
    the signature a flapping fault is made of - `flag-service-crashloop` is nothing but
    that shape.

    `revert` marks episodes that began after the fault was removed. Reverting recreates a
    container, and the recreate produces its own failures: in the cart-redis-misconfig
    bundle emailservice went to a 100% error ratio for about 75 seconds starting 28 seconds
    after the revert, having been at 0% for the entire incident. That is signal about the
    recovery, not about the fault, and counting it as blast radius blames the fault for
    damage the fix did.
    """
    data = payload.get("data")
    results = data.get("result", []) if isinstance(data, dict) else []
    floor = None if since is None else since.timestamp()
    gap = max(2 * step, 60)

    intervals: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        labels = item.get("metric", {})
        if not isinstance(labels, dict):
            continue
        stamps = sorted(
            float(v[0])
            for v in item.get("values", [])
            if isinstance(v, list) and len(v) == 2 and (floor is None or float(v[0]) >= floor)
        )
        if not stamps:
            continue

        episode = [stamps[0]]
        episodes: list[list[float]] = []
        for previous, current in pairwise(stamps):
            if current - previous > gap:
                episodes.append(episode)
                episode = [current]
            else:
                episode.append(current)
        episodes.append(episode)

        for points in episodes:
            began = datetime.fromtimestamp(points[0], tz=UTC)
            entry: dict[str, Any] = {
                "alert": labels.get("alertname"),
                "service": labels.get("service_name"),
                "first_seen": stamp(began),
                "last_seen": stamp(datetime.fromtimestamp(points[-1], tz=UTC)),
                "minutes_firing": round(len(points) * step / 60, 1),
            }
            if revert is not None:
                # Omitted rather than defaulted to False when there is no revert to
                # compare against - a baseline capture has none, and False would assert
                # something the data cannot support.
                entry["began_after_revert"] = began > revert
            intervals.append(entry)
    return sorted(intervals, key=lambda i: str(i["first_seen"]))
