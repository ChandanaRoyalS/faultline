"""What one world's span metrics are called and how widely they are smoothed (T7.1).

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

**The rate window is here for the same reason and was added later, at a cost.** It was hard-coded
`[2m]` in both query builders. When the v2 alert rules widened to `[5m]` (2026-09-22) the capture
did not follow, and a capture in that state writes `[2m]` statistics beside a `[5m]` alert series -
two instruments in one summary, contradicting each other, with nothing to say which is which. One
object per world is what makes the pairing unrepresentable.

**Why a world object and not a rename.** The same expressions are sent from three places - the
agent's own metric tool (`faultline.tools.metrics.render_query`), the harness's capture and baseline
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
class WorldMetrics:
    """How one world's span metrics are spelled and smoothed.

    **Named for the world rather than for the names** since 2026-09-22, when the rate window
    joined them. It was `SpanMetricNames`, and a type holding a window under that name would have
    been a lie of exactly the kind this module exists to prevent.
    """

    calls: str
    """The request counter. Carries `service_name` and `status_code` labels in both worlds."""

    duration_bucket: str
    """The latency histogram's bucket series, for `histogram_quantile`.

    **Both worlds measure milliseconds**, so a threshold in ms is comparable across the rename -
    which is the only reason the alert thresholds could be carried over at all, and they are still
    marked as unbaselined on v2 until measured there.
    """

    latency_span_filter: str
    """A label matcher narrowing which spans count as this world's latency, or `""` for all.

    **v2 excludes `SPAN_KIND_INTERNAL` and that is measured** (2026-09-22). `accounting` reported a
    p95 of 15000 ms on a healthy world, which is the histogram's top bucket boundary and therefore
    means "off the top of the scale, value unknown". The cause is in the demo's own
    `src/accounting/Consumer.cs`:

        using var activity = MyActivitySource.StartActivity(
            "order-consumed", ActivityKind.Internal);
        var consumeResult = _consumer.Consume();   // blocks until a message arrives
        ProcessMessage(consumeResult.Message);

    The span opens before a blocking consume, so its duration is the wait for the next order. Order
    arrivals are near-Poisson, so the p95 gap is about three times the mean: at the measured 0.154
    orders/s that is **19.4 s**, and at the 5-user rate of 0.078/s it is **38 s** - both above the
    15 s ceiling, which is why the first capture was pinned flat and the second only dipped below.

    **An internal span is bookkeeping or a background loop.** It is either already inside an
    enclosing request span, or it is not request work at all. Excluding the kind rather than naming
    `order-consumed` keeps the rule free of service-specific names and covers the next service that
    does this.

    **Measured against the alternatives rather than chosen** (2026-09-22, quiet world):

        all spans                          accounting 15000 ms   18
        SPAN_KIND_SERVER|CONSUMER only     accounting    95 ms   17 - load-generator VANISHES
        span_kind != INTERNAL              accounting    90 ms   18 - nothing lost

    The middle one also drops `SPAN_KIND_CLIENT`, which would have made a slow database in
    `accounting` undetectable: its inbound span is the Kafka delivery, and its actual work happens
    after that span closes, visible only through its `postgresql` client span.

    **v1 is `""` and stays there.** Every published figure was measured over all spans, and the
    freeze in `tests/test_spanmetrics.py` renders that byte for byte.
    """

    rate_window: str
    """The PromQL `rate()` window every query about this world uses, as `2m` / `5m`.

    **It lives here so that it cannot disagree with the world it describes**, which it did for
    four hours on 2026-09-22. The v2 alert rules widened to `[5m]` after the first baseline
    measured most of the world at 0.05-0.15 req/s; the capture queries kept a hard-coded `[2m]`
    because T7.1 parameterised the *names* and not the window. Nothing failed. A capture taken in
    that state reports `[2m]` statistics in its tables - 15000 ms p95s, error ratios to 100% - and
    a `[5m]` alert series beside them that is empty, and the two halves of one summary contradict
    each other with no indication which is the instrument.

    **Not `WindowPolicy`, which is a different quantity.** That class bounds which *timestamps* a
    range query fetches; this is the smoothing interval inside the expression. They are both
    called windows and they are not the same thing.
    """

    def latency_selector(self, *matchers: str) -> str:
        """The `{...}` for this world's duration histogram, or `""` when nothing narrows it.

        Built here rather than at each call site so that **a world's span filter cannot be applied
        to one query and forgotten at another** - the failure this module exists to prevent, in its
        third variation. `matchers` come first so v1 renders byte for byte what it always did.
        """
        parts = [m for m in (*matchers, self.latency_span_filter) if m]
        return "{" + ",".join(parts) + "}" if parts else ""


V1 = WorldMetrics(
    calls="calls_total",
    duration_bucket="latency_bucket",
    rate_window="2m",
    latency_span_filter="",
)
"""OTel Demo v1.2.1: `spanmetrics` as a processor. The world every published figure was measured
on (ADR-0026)."""

V2 = WorldMetrics(
    calls="traces_span_metrics_calls_total",
    duration_bucket="traces_span_metrics_duration_milliseconds_bucket",
    rate_window="5m",
    latency_span_filter='span_kind!="SPAN_KIND_INTERNAL"',
)
"""OTel Demo v2.x: `spanmetrics` as a connector (ADR-0042)."""

BY_WORLD: dict[str, WorldMetrics] = {"v1": V1, "v2": V2}
"""Selected by `ToolSettings.world`. An unknown key raises rather than falling back to V1: a
silent fallback here produces exactly the empty-result failure this module exists to prevent."""


def metrics_for(world: str) -> WorldMetrics:
    """One world's metric spelling and window, or a loud failure.

    **No default and no fallback**, deliberately. Every failure mode this module guards against is
    silent, so the one place that could reintroduce one is a lenient lookup.
    """
    try:
        return BY_WORLD[world]
    except KeyError:
        known = ", ".join(sorted(BY_WORLD))
        raise ValueError(
            f"unknown world {world!r} for span metrics; known worlds are {known}. "
            "A wrong name here is an empty PromQL result rather than an error, so this refuses "
            "rather than guessing."
        ) from None
