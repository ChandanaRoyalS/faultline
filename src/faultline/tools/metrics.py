"""Templated metric queries, baseline comparison and change points (T3.3b).

The plan's T3.3b: *"Promote T2.7's thin-slice prototype into the full specialist the spec's agent
table describes: baseline range-query comparison (incident window vs. normal), saturation /
error-rate / latency anomaly extraction, change-point timestamps."* Method: *"The PromQL tool
gets the same parse-validate-and-cap treatment as LogQL (query-language sandboxing parity);
baseline-comparison queries templated; standard typed evidence out."*

## Sandboxing parity, which is what "templated" buys

`logql_query` takes a **service** and builds the selector itself; no caller anywhere writes
LogQL. `promql_query` took a **query string**, and while nothing in the pipeline lets a model
reach that parameter, the asymmetry was real: one tool constructs its query language and the
other accepts it. The templates here close that - a metric query is named by a
`MetricTemplate` and rendered against a canonical service, so the *only* PromQL this system
sends is PromQL it wrote.

`promql_query` keeps its string parameter. Removing it would break the read-only URL test and
the harness's own recorded queries, and the parity the plan asks for is that a *specialist* has
a templated path, not that no such parameter exists.

## The four templates are the four the recorder already captures

`evalharness.prom.METRIC_QUERIES` has taken `error-ratio`, `call-rate` and `latency-p95` on
every bundle ever recorded, and `RUNTIME_FAMILIES` covers the fifth capture. Using the same
expressions is not laziness: **every recorded bundle in this repository holds those series**,
so a comparison the specialist makes live is comparable with what the corpus already contains,
and a narrative citing one can be checked against the other.

## Change points are computed, not asked

A change point is the first timestamp at which a series leaves its baseline and stays out. The
rule is arithmetic and stated: *baseline mean plus three standard deviations, floored at the
template's own alerting threshold, sustained for `PERSIST` consecutive samples.* Three sigma
alone is not enough on a world whose healthy baselines are frequently **exactly zero** - the
error ratio's healthy value is 0 and its standard deviation with it, so any single nonzero
sample would qualify as a change. The floor is what makes it a finding rather than noise, and
each floor is the number the alert rules already fire on (`compose/prometheus/alert-rules.yml`):
5% for the error ratio, 250ms for p95 latency.

**`PERSIST` is 3 samples**, which at the recorder's 15s scrape is 45 seconds. The alert rules
themselves wait 2-3 minutes; this is deliberately shorter, because the alert must not fire on a
blip and this must not *miss* the moment a blip became a fault. A change point is a timestamp to
investigate, not a claim that anything is wrong.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, tzinfo
from enum import StrEnum

PERSIST = 3
"""Consecutive samples beyond the threshold before a departure is a change point."""

SIGMA = 3.0
"""How many standard deviations from the baseline mean counts as leaving it."""


class MetricTemplate(StrEnum):
    """The metric questions this system knows how to ask. **Nothing else is sent.**"""

    ERROR_RATIO = "error-ratio"
    CALL_RATE = "call-rate"
    LATENCY_P95 = "latency-p95"
    RUNTIME_MEMORY = "runtime-memory"
    """The saturation half of the plan's *"saturation / error-rate / latency"*, as far as this
    world can answer it. ADR-0024 measured that no alert rule sees saturation (Q13) and ADR-0029
    that the `scale` class has no mechanism here - but the **series exist**: every scenario
    bundle captures `process_runtime_*` / `system_memory_*`, which is what a responder reads to
    say a service was running out of memory. The gap is an alert, not a metric, and a specialist
    that can query the series is not blocked by the missing rule."""


FLOORS: dict[MetricTemplate, float] = {
    MetricTemplate.ERROR_RATIO: 0.05,
    MetricTemplate.LATENCY_P95: 250.0,
    MetricTemplate.CALL_RATE: 0.0,
    MetricTemplate.RUNTIME_MEMORY: 0.0,
}
"""The absolute departure each template needs before three sigma means anything.

The two that have one are the two the alert rules name, at the rules' own numbers - 5% error
ratio, 250ms p95 - so a change point and an alert are talking about the same event. The other
two are 0.0 and that is honest rather than lazy: **this repository has no measured threshold for
a meaningful change in call rate or memory**, so those templates report three-sigma departures
and say so, and a floor invented here would be a number nobody could defend.
"""


def render_query(template: MetricTemplate, service: str) -> str:
    """One template, scoped to one service. The only PromQL this layer sends.

    Expressions match `evalharness.prom.METRIC_QUERIES` so a live comparison and a recorded
    bundle describe the same series. `service_name` is the span-metrics label; the runtime
    families carry `exported_job` instead, which ADR-0019 recorded as measured - Prometheus
    renamed the exporter's `job` label, and `recommendation-memory-squeeze`'s investigation
    turns on their absence.
    """
    if template is MetricTemplate.ERROR_RATIO:
        return (
            f'sum by(service_name) (rate(calls_total{{service_name="{service}",'
            'status_code="STATUS_CODE_ERROR"}[2m])) '
            f'/ sum by(service_name) (rate(calls_total{{service_name="{service}"}}[2m]))'
        )
    if template is MetricTemplate.CALL_RATE:
        return f'sum by(service_name) (rate(calls_total{{service_name="{service}"}}[2m]))'
    if template is MetricTemplate.LATENCY_P95:
        return (
            "histogram_quantile(0.95, sum by(service_name, le) "
            f'(rate(latency_bucket{{service_name="{service}"}}[2m])))'
        )
    return (
        "sum by(exported_job) "
        f'({{__name__=~"process_runtime_.*|runtime_.*|system_memory_.*",exported_job="{service}"}})'
    )


@dataclass(frozen=True, slots=True)
class Summary:
    """What one window of one series looked like."""

    samples: int
    mean: float
    minimum: float
    maximum: float
    stdev: float

    def render(self) -> str:
        return (
            f"n={self.samples} mean={self.mean:.4g} min={self.minimum:.4g} "
            f"max={self.maximum:.4g} sd={self.stdev:.4g}"
        )


EMPTY = Summary(samples=0, mean=0.0, minimum=0.0, maximum=0.0, stdev=0.0)


def defined(points: list[tuple[float, float]]) -> tuple[list[tuple[float, float]], int]:
    """The samples that have a value, and a count of the ones that do not.

    **`NaN` is what Prometheus returns for `0/0`**, and the error-ratio template is a division:
    a service with no traffic in an interval has no error *ratio*, not a ratio of zero. Every
    scenario in this catalog that stops a service produces these, which is why the first live
    run to hit one was the first scenario whose service actually died.

    They are dropped from the arithmetic and **counted**, never coerced. Reading `NaN` as `0.0`
    would say the service was serving perfectly at the moment it was serving nothing, which is
    the inverse of the truth and would hide the very shape `ServiceNoTraffic` exists to catch.
    The count travels onto the result, so an undefined interval is visible as one.

    Found by `cart-bad-image-tag`, which discarded on `statistics.stdev` raising
    `AttributeError: 'float' object has no attribute 'numerator'` - the standard library's way
    of saying a `NaN` reached its exact-ratio arithmetic.
    """
    kept = [(at, value) for at, value in points if math.isfinite(value)]
    return kept, len(points) - len(kept)


def summarise(points: list[tuple[float, float]]) -> Summary:
    values = [value for _, value in points]
    if not values:
        return EMPTY
    return Summary(
        samples=len(values),
        mean=statistics.fmean(values),
        minimum=min(values),
        maximum=max(values),
        stdev=statistics.stdev(values) if len(values) > 1 else 0.0,
    )


def threshold_for(template: MetricTemplate, baseline: Summary) -> float:
    """Where this series has to go before it has left its baseline."""
    return max(baseline.mean + SIGMA * baseline.stdev, baseline.mean + FLOORS[template])


@dataclass(frozen=True, slots=True)
class ChangePoint:
    """When a series left its baseline and stayed out."""

    at: datetime
    value: float
    threshold: float

    def render(self) -> str:
        return f"{self.at.isoformat()}  value {self.value:.4g} crossed {self.threshold:.4g}"


def change_points(
    points: list[tuple[float, float]],
    template: MetricTemplate,
    baseline: Summary,
    tz: tzinfo | None = None,
) -> list[ChangePoint]:
    """Every sustained departure, in time order. **At most one per departure.**

    A series that crosses, returns and crosses again reports two change points, which answers a
    responder's actual question - *did it recover?* - by the shape of the list rather than by
    prose. A series that crosses once and stays out reports one, not one per sample.

    **The timestamp is the first sample of the run**, not the sample that completed it. The
    question a change point answers is *when did this start*, and reporting the moment the
    persistence rule was satisfied would put every change point `PERSIST` samples late.
    """
    if baseline.samples == 0:
        # Nothing to depart from. Reported as no change points rather than as every point being
        # one: an unobserved baseline is not a flat baseline (ADR-0019's distinction, again).
        return []
    threshold = threshold_for(template, baseline)
    found: list[ChangePoint] = []
    run_start: int | None = None
    reported = False
    for index, (_, value) in enumerate(points):
        if value > threshold:
            if run_start is None:
                run_start = index
                reported = False
            if not reported and index - run_start + 1 >= PERSIST:
                at, first = points[run_start]
                found.append(
                    ChangePoint(
                        at=datetime.fromtimestamp(at, tz=tz), value=first, threshold=threshold
                    )
                )
                reported = True
        else:
            run_start = None
            reported = False
    return found
