"""The v2 world's overlay, and the three ways it can break without telling anyone (T7.1).

Every guard here exists because the failure it catches is **silent**: a container that starts
cleanly, stays healthy, logs nothing unusual, and produces no telemetry. The v1 world's equivalent
defects announced themselves - a missing image fails to start, a bad config refuses to parse. These
do not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = REPO_ROOT / "compose"

yaml = pytest.importorskip("yaml", reason="pyyaml is a dev dependency; the guards need a parser")


def telemetry_v2() -> dict:
    return yaml.safe_load((COMPOSE / "telemetry-v2.yml").read_text())


def test_the_v2_prometheus_overlay_keeps_the_otlp_receiver() -> None:
    """**The one flag whose absence produces no error anywhere** (T7.1, 2026-09-22).

    v1's collector exposes a Prometheus exporter and Faultline's config scrapes it. **v2's
    collector pushes instead** - its metrics pipeline ends `exporters: [otlphttp/prometheus,
    debug]`, aimed at `http://prometheus:9090/api/v1/otlp` - and v2's Prometheus accepts that only
    because it runs with `--web.enable-otlp-receiver`.

    Faultline's overlay replaces `command:` wholesale in order to point Prometheus at its own
    config and rules. An overlay that forgets this flag leaves a Prometheus that **starts, stays
    healthy, scrapes its one job, and receives no application metric at all** - no failing
    container, nothing in any log, and all three alert rules evaluating forever against an empty
    series. The world would look up and be blind.
    """
    command = telemetry_v2()["services"]["prometheus"]["command"]

    assert "--web.enable-otlp-receiver" in command, (
        "compose/telemetry-v2.yml drops --web.enable-otlp-receiver from Prometheus's command. "
        "v2's collector pushes metrics over OTLP rather than being scraped, so without it "
        "Prometheus receives nothing and reports no error."
    )


def test_the_v2_collector_extras_restate_every_exporter_they_replace() -> None:
    """**The collector merges config lists by replacing them, not appending** (v1's lesson, v2's
    list).

    `otelcol-extras-v2.yml` is the collector's second `--config`, and it names the traces
    exporters in order to add Tempo. Because the merge replaces, the file must restate v2's own
    three or they are silently dropped:

    - `otlp` - Jaeger. The demo's trace UI goes dark.
    - `debug` - v2's replacement for v1's `logging`.
    - `spanmetrics` - **the connector every alert rule depends on.** v2 wires spanmetrics as an
      exporter on the traces pipeline, so dropping it here stops `traces_span_metrics_*` being
      produced at all, and all three rules go quiet on a world that is still breaking.
    """
    extras = yaml.safe_load((COMPOSE / "otelcol-extras-v2.yml").read_text())
    exporters = extras["service"]["pipelines"]["traces"]["exporters"]

    for required in ("otlp", "debug", "spanmetrics", "otlp/tempo"):
        assert required in exporters, (
            f"compose/otelcol-extras-v2.yml drops {required!r} from the traces exporters. "
            "The collector replaces lists rather than appending to them, so every exporter v2 "
            "declares must be restated here alongside otlp/tempo."
        )


def test_the_v2_alert_rules_use_the_connector_metric_names() -> None:
    """**v1's metric names exist in v2 and mean nothing there** (T7.1, 2026-09-22).

    v1 runs `spanmetrics` as a processor and emits `calls_total` / `latency_bucket`. v2 runs it as
    a connector, which emits under a `traces_span_metrics_` namespace with the histogram in
    milliseconds. The names were read off v2's own Grafana dashboards at tag 2.2.0 rather than
    inferred from the connector's documented defaults.

    A rule left on the v1 names does not fail to load - PromQL over a metric that does not exist is
    an empty series, which evaluates cleanly and never fires. **A benchmark whose alerts never fire
    scores every scenario as a miss and looks like an agent problem.**
    """
    rules = yaml.safe_load((COMPOSE / "prometheus" / "alert-rules-v2.yml").read_text())
    expressions = [r["expr"] for g in rules["groups"] for r in g["rules"]]

    assert expressions, "no rules found in alert-rules-v2.yml"

    for expr in expressions:
        assert "traces_span_metrics_" in expr, f"a v2 rule uses no connector metric: {expr!r}"

    joined = "\n".join(expressions)
    for stale in ("calls_total{", "rate(calls_total", "latency_bucket"):
        assert stale not in joined.replace("traces_span_metrics_calls_total", "X"), (
            f"compose/prometheus/alert-rules-v2.yml still names the v1 metric {stale!r}. "
            "On v2 that is an empty series: the rule loads, evaluates and never fires."
        )


def test_the_v1_world_is_untouched_by_the_v2_overlay() -> None:
    """The migration is a re-founding, and both worlds exist until the new one has a record.

    `world-v2-up` is a parallel target precisely so that trying v2 cannot break the world every
    published figure was measured on. If the v2 files ever start referencing v1's, that separation
    has quietly ended.
    """
    v2_files = [
        COMPOSE / "telemetry-v2.yml",
        COMPOSE / "world-v2.override.yml",
        COMPOSE / "otelcol-extras-v2.yml",
    ]
    for path in v2_files:
        text = path.read_text()
        for v1_only in ("world-arm64.override.yml", "otelcol-extras.yml"):
            assert v1_only not in text.split("# ")[0] + "".join(
                line for line in text.splitlines(keepends=True) if not line.lstrip().startswith("#")
            ), f"{path.name} references the v1 file {v1_only} outside a comment"
