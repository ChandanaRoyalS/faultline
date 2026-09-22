"""The span-metric names, and the freeze that makes parameterising them safe (T7.1).

`faultline.tools.spanmetrics` exists because v1 wires the collector's `spanmetrics` as a processor
and v2 as a connector, so the two worlds emit different series names for the same quantity. Making
every PromQL site take a name set is only safe if **the v1 rendering does not move**, because every
published figure was measured through those exact expressions.

So the strings below are frozen verbatim. They are what the tree produced before this module
existed, copied from the v1 source rather than regenerated from it — a test that asks the code what
it currently emits and asserts that it emits it would pass through any change at all.
"""

from __future__ import annotations

import pytest

from evalharness.prom import METRIC_QUERIES, metric_queries
from faultline.tools.metrics import MetricTemplate, render_query
from faultline.tools.settings import ToolSettings
from faultline.tools.spanmetrics import BY_WORLD, V1, V2, names_for

# --- the freeze ---------------------------------------------------------------------------

V1_RENDER_QUERY = {
    MetricTemplate.ERROR_RATIO: (
        'sum by(service_name) (rate(calls_total{service_name="cartservice",'
        'status_code="STATUS_CODE_ERROR"}[2m])) '
        '/ sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))'
    ),
    MetricTemplate.CALL_RATE: (
        'sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))'
    ),
    MetricTemplate.LATENCY_P95: (
        "histogram_quantile(0.95, sum by(service_name, le) "
        '(rate(latency_bucket{service_name="cartservice"}[2m])))'
    ),
}

V1_CAPTURE = {
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


@pytest.mark.parametrize("template", list(V1_RENDER_QUERY))
def test_the_agents_v1_queries_are_byte_for_byte_what_they_were(template: MetricTemplate) -> None:
    """**The whole safety argument for parameterising these.** 197 scored runs, six dev sweeps and
    three holdout entries were measured through these exact expressions. If the v1 rendering moves
    by a character, the migration has silently changed what the agent asks of the world every
    published figure describes."""
    assert render_query(template, "cartservice") == V1_RENDER_QUERY[template]


def test_the_harness_v1_capture_is_byte_for_byte_what_it_was() -> None:
    """The same freeze for the capture set, which every bundle under `evals/runs/` was taken
    with."""
    assert METRIC_QUERIES == V1_CAPTURE
    assert metric_queries() == V1_CAPTURE
    assert metric_queries(V1) == V1_CAPTURE


def test_v1_is_the_default_everywhere_it_could_be_defaulted() -> None:
    """**A world is opted into, never defaulted into.** A default of v2 anywhere would point a v1
    run at a series that does not exist, and PromQL over a missing metric is an empty result rather
    than an error - so the run would succeed, report no data and look like a quiet world."""
    assert ToolSettings().world == "v1"
    assert names_for(ToolSettings().world) is V1


# --- the v2 set ---------------------------------------------------------------------------


def test_the_two_worlds_share_no_metric_name() -> None:
    """If a name were shared, a half-finished migration would work for one query and silently
    return nothing for another - the hardest version of this failure to notice."""
    assert {V1.calls, V1.duration_bucket}.isdisjoint({V2.calls, V2.duration_bucket})


def test_every_v2_query_names_only_v2_metrics() -> None:
    v2 = metric_queries(V2)
    joined = " ".join(v2.values())

    assert set(v2) == set(METRIC_QUERIES), "the two worlds must capture the same four series"
    assert V2.calls in joined and V2.duration_bucket in joined
    assert "latency_bucket" not in joined
    # `calls_total` is a substring of `traces_span_metrics_calls_total`, so the v1 name is only
    # really absent once the v2 one is masked out.
    assert "calls_total" not in joined.replace(V2.calls, "")


def test_an_unknown_world_raises_rather_than_falling_back() -> None:
    """**The one place that could reintroduce a silent failure is a lenient lookup.** Falling back
    to v1 for an unrecognised world is exactly the empty-result-not-an-error mode this module was
    written to prevent."""
    with pytest.raises(ValueError, match="unknown world"):
        names_for("v3")

    assert set(BY_WORLD) == {"v1", "v2"}
