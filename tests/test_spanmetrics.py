"""One world's metric spelling and window, and the freeze that makes both safe to vary (T7.1).

`faultline.tools.spanmetrics` exists because v1 wires the collector's `spanmetrics` as a processor
and v2 as a connector, so the two worlds emit different series names for the same quantity. It also
carries the `rate()` window, added 2026-09-22 after the v2 alert rules widened to `[5m]` and the
capture queries silently stayed on `[2m]`. Making every PromQL site take that object is only safe
if **the v1 rendering does not move**, because every published figure was measured through those
exact expressions.

So the strings below are frozen verbatim. They are what the tree produced before this module
existed, copied from the v1 source rather than regenerated from it — a test that asks the code what
it currently emits and asserts that it emits it would pass through any change at all.
"""

from __future__ import annotations

import pytest

from evalharness.prom import METRIC_QUERIES, metric_queries
from faultline.tools.metrics import MetricTemplate, render_query
from faultline.tools.settings import ToolSettings
from faultline.tools.spanmetrics import BY_WORLD, V1, V2, metrics_for

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
    assert metrics_for(ToolSettings().world) is V1


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


def test_the_v2_queries_smooth_over_v2s_window_and_never_v1s() -> None:
    """**The window is part of a world's identity, not a constant** (2026-09-22).

    v1 smooths over `[2m]`, which its own baseline validated. v2 needs `[5m]`: at 25 users most of
    the world still runs at 0.1-0.3 req/s, and `image-provider` does not respond to load at all, so
    a `[2m]` window holds six to eight samples and a p95 over six spans is the maximum of six spans.

    A v2 query left on `[2m]` does not fail. It reports 15000 ms p95s and error ratios to 100% on a
    healthy world - and it did, twice, in captures that were read as findings about the world.
    """
    assert V1.rate_window == "2m"
    assert V2.rate_window == "5m"

    v2 = " ".join(metric_queries(V2).values())
    assert "[5m]" in v2
    assert "[2m]" not in v2

    agent_v2 = " ".join(render_query(t, "cart", V2) for t in MetricTemplate)
    assert "[2m]" not in agent_v2, (
        "the agent's own metric tool still smooths a v2 query over v1's window"
    )


def test_v1s_latency_selector_adds_nothing_and_v2s_adds_exactly_one_matcher() -> None:
    """**The freeze above already proves v1 is unchanged; this says why it is allowed to be.**

    `latency_selector` is the one place a world's span filter is applied, so that it cannot be
    applied to one query and forgotten at another. For v1 it must collapse to nothing at all -
    not to `{}`, which is a parse error, and not to a matcher - or every published figure's
    expression moves.
    """
    assert V1.latency_span_filter == ""
    assert V1.latency_selector() == ""
    assert V1.latency_selector('service_name="cartservice"') == '{service_name="cartservice"}'

    assert V2.latency_span_filter == 'span_kind!="SPAN_KIND_INTERNAL"'
    assert V2.latency_selector() == '{span_kind!="SPAN_KIND_INTERNAL"}'
    assert V2.latency_selector('service_name="cart"') == (
        '{service_name="cart",span_kind!="SPAN_KIND_INTERNAL"}'
    )


def test_the_v2_latency_queries_exclude_internal_spans_and_the_others_do_not() -> None:
    """**Scoped to duration, because that is where it was measured.** `order-consumed` inflated a
    p95; it produced no errors and it is not what keeps `accounting` looking alive. Filtering the
    call counter too would cost error visibility for symmetry."""
    v2 = metric_queries(V2)

    assert V2.latency_span_filter in v2["latency-p95"]
    assert V2.latency_span_filter not in v2["error-ratio"]
    assert V2.latency_span_filter not in v2["call-rate"]

    agent = render_query(MetricTemplate.LATENCY_P95, "accounting", V2)
    assert V2.latency_span_filter in agent
    assert V2.latency_span_filter not in render_query(MetricTemplate.CALL_RATE, "accounting", V2)


def test_an_unknown_world_raises_rather_than_falling_back() -> None:
    """**The one place that could reintroduce a silent failure is a lenient lookup.** Falling back
    to v1 for an unrecognised world is exactly the empty-result-not-an-error mode this module was
    written to prevent."""
    with pytest.raises(ValueError, match="unknown world"):
        metrics_for("v3")

    assert set(BY_WORLD) == {"v1", "v2"}


def test_the_baseline_recorder_cannot_capture_one_worlds_queries_against_another() -> None:
    """**A capture's provenance is its summary, and a summary can lie silently** (T7.1).

    `evalharness.baseline` writes the expressions it used into `summary.md` beside the numbers
    they produced. While it read the module-level `METRIC_QUERIES`, a `--world v2` capture would
    have queried v2 and *documented v1* - or, worse, queried v1's names against a v2 Prometheus and
    written a summary full of empty series with no indication anything was wrong, because PromQL
    over a missing metric is an empty result rather than an error.

    Read as source rather than by running the recorder, which needs a live Prometheus and a
    forty-five minute window.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "src/evalharness/baseline.py").read_text()
    body = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))

    assert "METRIC_QUERIES" not in body, (
        "evalharness/baseline.py references the v1 METRIC_QUERIES constant. It takes --world, so "
        "every query and the summary that documents them must come from metric_queries(metrics)."
    )
    assert "metrics_for(world)" in body, (
        "the baseline recorder should resolve the world it was asked to measure"
    )
    assert "metric_queries(metrics)" in body, (
        "the baseline recorder should build its queries from the world it was asked to measure, "
        "so that the expressions it runs and the ones it writes into summary.md are one object - "
        "metric names and rate window together, which is why they live on one dataclass."
    )


# --- the recorded evidence, which is the expensive place to get this wrong -------------------


def _source(relative: str) -> str:
    """A module's code with comment lines removed, so a guard reads what runs."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / relative).read_text()
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def test_the_scenario_bundle_captures_the_world_it_was_recorded_on() -> None:
    """**The most expensive version of the empty-series failure** (2026-09-22).

    `evalharness.rehearse` built a scenario bundle's four captures from the module-level
    `METRIC_QUERIES` - v1's names, hard-coded. A bundle recorded on the v2 world would have held
    four empty series, because `calls_total` and `latency_bucket` do not exist there and PromQL
    over a missing metric is an empty result rather than an error.

    **The bundle is what a run is scored against and what the agent reads.** The run would have
    completed, the agent would have found nothing because it was shown nothing, and the miss would
    have been recorded as a fact about the agent. Unlike the gate - which refuses, and whose
    blindness cost only that refusal - this one writes a wrong answer into the corpus.
    """
    body = _source("src/evalharness/rehearse.py")

    assert "**METRIC_QUERIES" not in body, (
        "rehearse builds a bundle's captures from the v1 constant. On any other world that is "
        "four empty series in a recorded bundle, which reads as a quiet world rather than as an "
        "error, and the run scores a miss the agent did not make."
    )
    assert "metric_queries(world_metrics)" in body
    assert "metrics_for(ToolSettings().world)" in body


def test_the_b0_baseline_asks_its_own_world_rather_than_the_default() -> None:
    """`render_query` defaults to v1 so the frozen expressions stay frozen - which means **a
    caller that forgets to say which world it is on silently asks v1's question.** B0's
    error-ratio delta is its only metric signal, and an empty one reads as "no service moved",
    which B0 would then report as its finding."""
    body = _source("src/evalharness/baselines.py")

    assert "render_query(MetricTemplate.ERROR_RATIO, service)" not in body, (
        "B0 renders its error-ratio query without a world, so it asks v1's names everywhere. "
        "On v2 that is an empty result, and an empty delta is a finding B0 will report."
    )
    assert "metrics_for(ToolSettings().world)" in body
