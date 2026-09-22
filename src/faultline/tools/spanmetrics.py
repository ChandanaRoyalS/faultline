"""The span-metric names, in one place, because two worlds spell them differently (T7.1).

**Why this module exists.** Every PromQL this project sends about a service's health reads two
series produced by the collector's `spanmetrics`: a call counter and a duration histogram. Their
names are not a property of Faultline - they are a property of **how the collector is wired in the
world being observed**, and the two worlds wire it differently:

- **OTel Demo v1.2.1** runs `spanmetrics` as a **processor** in the traces pipeline
  (`processors: [memory_limiter, spanmetrics, batch]`) and emits `calls_total` / `latency_bucket`.
- **OTel Demo v2.2.0** runs it as a **connector** - an exporter on traces, a receiver on metrics
  (`exporters: [otlp, debug, spanmetrics]`) - and emits under a `traces_span_metrics_` namespace
  with the histogram in milliseconds.

**The names were read off v2's own Grafana dashboards** at tag 2.2.0, which query them directly,
rather than inferred from the connector's documented defaults.

**Why a name set and not a rename.** The same expressions are sent from three places - the agent's
own metric tool (`faultline.tools.metrics.render_query`), the harness's capture and baseline
(`evalharness.prom.METRIC_QUERIES`), and the pre-flight gate - and the alert rules say the same
thing again in YAML. A migration that renamed them in some and not others would leave the rest
querying a series that does not exist, and **PromQL over a missing metric is an empty result, not
an error**: the query succeeds, the agent reads "no data", the gate sees no traffic, and every
alert rule evaluates cleanly and never fires. Nothing anywhere fails loudly. One source, selected
by configuration, is the only shape that cannot drift.

**V1 is the default and its rendering is frozen.** `tests/test_spanmetrics.py` asserts the v1
expressions byte for byte against what the tree produced before this module existed, so no recorded
run's behaviour changes and neither stamp moves. A world is opted into, never defaulted into.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpanMetricNames:
    """What the collector in a given world calls its two span-metric series."""

    calls: str
    """The request counter. Carries `service_name` and `status_code` labels in both worlds."""

    duration_bucket: str
    """The latency histogram's bucket series, for `histogram_quantile`.

    **Both worlds measure milliseconds**, so a threshold in ms is comparable across the rename -
    which is the only reason the alert thresholds could be carried over at all, and they are still
    marked as unbaselined on v2 until measured there.
    """


V1 = SpanMetricNames(calls="calls_total", duration_bucket="latency_bucket")
"""OTel Demo v1.2.1: `spanmetrics` as a processor. The world every published figure was measured
on (ADR-0026)."""

V2 = SpanMetricNames(
    calls="traces_span_metrics_calls_total",
    duration_bucket="traces_span_metrics_duration_milliseconds_bucket",
)
"""OTel Demo v2.x: `spanmetrics` as a connector (ADR-0042)."""

BY_WORLD: dict[str, SpanMetricNames] = {"v1": V1, "v2": V2}
"""Selected by `ToolSettings.world`. An unknown key raises rather than falling back to V1: a
silent fallback here produces exactly the empty-result failure this module exists to prevent."""


def names_for(world: str) -> SpanMetricNames:
    """The name set for a world, or a loud failure.

    **No default and no fallback**, deliberately. Every failure mode this module guards against is
    silent, so the one place that could reintroduce one is a lenient lookup.
    """
    try:
        return BY_WORLD[world]
    except KeyError:
        known = ", ".join(sorted(BY_WORLD))
        raise ValueError(
            f"unknown world {world!r} for span-metric names; known worlds are {known}. "
            "A wrong name here is an empty PromQL result rather than an error, so this refuses "
            "rather than guessing."
        ) from None
