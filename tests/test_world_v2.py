"""The v2 world's overlay, and the three ways it can break without telling anyone (T7.1).

Every guard here exists because the failure it catches is **silent**: a container that starts
cleanly, stays healthy, logs nothing unusual, and produces no telemetry. The v1 world's equivalent
defects announced themselves - a missing image fails to start, a bad config refuses to parse. These
do not.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = REPO_ROOT / "compose"

# `world-v2-up` runs `cd world-v2 && docker compose -f docker-compose.yml -f ../compose/...`, so
# every relative volume source in the overlay is resolved against the clone directory.
COMPOSE_PROJECT_DIR = REPO_ROOT / "world-v2"

yaml = pytest.importorskip("yaml", reason="pyyaml is a dev dependency; the guards need a parser")


def telemetry_v2() -> dict:
    return yaml.safe_load((COMPOSE / "telemetry-v2.yml").read_text())


def mounts(service: str) -> list[tuple[Path, str]]:
    """Every bind mount on `service` as `(host path, container path)`, relative sources resolved."""
    out: list[tuple[Path, str]] = []
    for spec in telemetry_v2()["services"][service].get("volumes", []):
        source, target = spec.split(":")[:2]
        if source.startswith("/"):  # /var/run/docker.sock and friends: not ours to resolve
            continue
        out.append(((COMPOSE_PROJECT_DIR / source).resolve(), target))
    return out


def host_path_for(service: str, container_path: str) -> Path | None:
    """Where a path inside `service` comes from on the host, or None if nothing mounts it."""
    for source, target in mounts(service):
        if container_path == target:
            return source
        if container_path.startswith(target.rstrip("/") + "/"):
            return source / container_path[len(target.rstrip("/")) + 1 :]
    return None


def config_file_flag(service: str) -> str:
    flags = [c for c in telemetry_v2()["services"][service]["command"] if "--config.file=" in c]
    assert len(flags) == 1, f"{service} should name exactly one --config.file, got {flags!r}"
    return flags[0].split("=", 1)[1]


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


def test_every_v2_rule_uses_the_measured_rate_window() -> None:
    """**The window is a measured value on v2, not a default** (2026-09-22).

    The first quiet baseline found most of the world at 0.05-0.15 req/s, so a `[2m]` window held
    six to eight samples on the quietest services and the rules reported 15000 ms p95s and 100%
    error ratios on a world with nothing injected. Raising the load bought 2.6-4.5x and **could
    not reach `image-provider` at all** - 0.100 req/s before and after - so the windows widened to
    `[5m]`, which clears thirty samples everywhere at 25 users.

    A rule left behind on `[2m]` would not fail: it would fire on noise, on a healthy world,
    intermittently, and look like a fault the agent failed to explain.
    """
    text = (COMPOSE / "prometheus" / "alert-rules-v2.yml").read_text()
    expressions = "\n".join(line for line in text.splitlines() if "traces_span_metrics_" in line)
    windows = set(re.findall(r"\[(\d+m)\](?:\s+offset)?", expressions))

    # `[30m] offset 10m` is ServiceNoTraffic's "was it serving before" lookback, a different
    # quantity from the detection window and deliberately long.
    detection = windows - {"30m"}

    assert detection == {"5m"}, (
        f"the v2 rules use rate windows {sorted(detection)}; the baseline measured [5m] as the "
        "window at which every service, image-provider included, clears thirty samples. A rule "
        "left on a narrower window fires on sampling noise rather than on faults."
    )


def test_the_v2_capture_window_is_the_window_the_v2_rules_evaluate() -> None:
    """**The capture and the rules are two views of one instrument, and they disagreed** (T7.1,
    2026-09-22).

    The alert rules widened to `[5m]` after the first baseline measured most of the world at
    0.05-0.15 req/s. The capture queries did not: T7.1 had parameterised the metric *names* for v2
    and left the rate window hard-coded at `[2m]` in `evalharness.prom.metric_queries` and
    `faultline.tools.metrics.render_query`.

    **Nothing failed, and the result would have been read backwards.** A capture in that state
    writes `[2m]` statistics into its tables - the same 15000 ms p95s and 100% error ratios the
    first baseline reported, because that is what six samples produce - and a `[5m]` `alerts-firing`
    series beside them which, if the widening worked, is empty. The obvious reading of that summary
    is "the world is still too noisy". The correct reading is that the tables and the alerts are
    measuring with different instruments.

    So the window lives on `WorldMetrics` beside the names, and this pins it to the rules.
    """
    from faultline.tools.spanmetrics import V2

    text = (COMPOSE / "prometheus" / "alert-rules-v2.yml").read_text()
    expressions = "\n".join(line for line in text.splitlines() if "traces_span_metrics_" in line)
    windows = set(re.findall(r"\[(\d+m)\](?:\s+offset)?", expressions)) - {"30m"}

    assert windows == {V2.rate_window}, (
        f"the v2 alert rules evaluate {sorted(windows)} and the v2 capture queries smooth over "
        f"[{V2.rate_window}]. A capture taken in that state reports one instrument's statistics "
        "beside the other's alerts, and the two contradict each other with nothing to say which "
        "is which."
    )


@pytest.mark.parametrize("service", ["prometheus", "alertmanager"])
def test_the_reloadable_services_mount_a_directory_not_a_file(service: str) -> None:
    """**A single-file bind mount binds the inode, and `git am` replaces the inode** (2026-09-22,
    `docs/evidence/world-v2-trial/2026-09-22-the-mount-that-detached.md`).

    Both of these services have a reload endpoint, so both are expected to pick up a config the
    repository has changed underneath them. Neither can, if its config is mounted file-by-file:
    `git am` writes a new file and renames it over the old, the running container's mount is left
    pointing at an inode the host directory no longer names, and the path inside the container
    becomes `ENOENT`.

    **Prometheus's response to that is to keep the rules it already has** - `error loading rules,
    previous rule set restored` - while every container reports `Running`, `docker compose up -d`
    recreates nothing (no compose *path* changed), and `/api/v1/rules` answers with the stale
    windows. It cost a 45-minute baseline that looked like a result.
    """
    binds = mounts(service)
    assert binds, f"{service} mounts nothing; its config has to come from somewhere"

    for source, target in binds:
        assert not source.is_file(), (
            f"compose/telemetry-v2.yml mounts {source.name} into {service} as a single file "
            f"({target}). A merge that rewrites that file detaches the mount from a running "
            "container, and Prometheus answers a failed reload by keeping its previous rules. "
            "Mount the containing directory instead."
        )


@pytest.mark.parametrize("service", ["prometheus", "alertmanager"])
def test_every_config_path_named_inside_the_v2_containers_is_a_file_we_ship(service: str) -> None:
    """**This guard protects the fix, and it would not have caught the bug.** Said plainly because
    the distinction is easy to blur and the record should not.

    The 2026-09-22 failure was a *runtime* detachment: the compose file and the config agreed
    perfectly, and the inode behind the mount was replaced while the container ran. No static check
    can see that. `test_the_reloadable_services_mount_a_directory_not_a_file` is what catches it,
    by removing the shape that permits it.

    What this guard catches is the hazard the fix *introduces*. The rule file's location is now
    spelled in two places - `--config.file` in `telemetry-v2.yml` and `rule_files` in the config it
    points at - and both are container paths, which no tool in `make check` can resolve.
    `promtool check config` cannot: run on a host, it reports `SUCCESS: 1 rule files found` for a
    path that does not exist inside the container, which is exactly what it reported while the
    world was broken. So this walks the bind mounts by hand and resolves every named container path
    back to a file this repository actually contains.

    It matters because Prometheus does not fail loudly when a rule file goes missing. It logs
    `loading groups failed`, restores its previous rule set, and keeps answering `/api/v1/rules`.
    """
    config_path = config_file_flag(service)
    config_source = host_path_for(service, config_path)

    assert config_source is not None, (
        f"{service}'s --config.file is {config_path}, which no bind mount in telemetry-v2.yml "
        "provides. The container would start against a path that does not exist."
    )
    assert config_source.is_file(), (
        f"{service}'s --config.file {config_path} resolves to {config_source}, which this "
        "repository does not contain."
    )

    if service != "prometheus":
        return

    for rule_path in yaml.safe_load(config_source.read_text())["rule_files"]:
        rule_source = host_path_for(service, rule_path)
        assert rule_source is not None, (
            f"{config_source.name} lists rule file {rule_path}, which no bind mount provides. "
            "Prometheus logs 'loading groups failed' and RESTORES ITS PREVIOUS RULE SET, so the "
            "world keeps alerting on whatever it happened to load at startup."
        )
        assert rule_source.is_file(), (
            f"{config_source.name} lists rule file {rule_path}, which resolves to {rule_source}, "
            "and this repository does not contain it."
        )


def test_the_v2_prometheus_does_not_mount_over_its_own_image_directories() -> None:
    """**Why the mount target is `/etc/faultline` and not `/etc/prometheus`.**

    The obvious directory mount - `compose/prometheus` over `/etc/prometheus` - would hide the
    image's own `consoles/` and `console_libraries/`, which two flags in the same `command:` point
    at. Fixing one silent breakage by introducing another is not a fix.
    """
    command = telemetry_v2()["services"]["prometheus"]["command"]
    referenced = [c.split("=", 1)[1] for c in command if c.startswith("--web.console.")]
    assert referenced, "the console flags were dropped; this guard has nothing left to protect"

    for _, target in mounts("prometheus"):
        for path in referenced:
            assert not path.startswith(target.rstrip("/") + "/"), (
                f"telemetry-v2.yml mounts {target} over {path}, which the image provides and "
                f"--web.console.* still points at."
            )
