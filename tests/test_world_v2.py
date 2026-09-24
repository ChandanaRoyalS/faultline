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


def test_the_v2_latency_rule_and_the_v2_capture_exclude_the_same_spans() -> None:
    """**The second half of "the capture and the rule are one instrument"** (T7.1, 2026-09-22).

    `ServiceHighLatency` excludes `SPAN_KIND_INTERNAL` because `accounting`'s `order-consumed` span
    wraps a blocking Kafka consume and measures the wait for the next order rather than any
    latency. A capture that did not exclude the same spans would report `accounting` at 15000 ms -
    the histogram's top boundary, meaning "above 15 s, unknown" - beside an alert series that never
    fires on it, which is the tables-contradict-the-alerts failure the rate window already taught
    us once.
    """
    from evalharness.prom import metric_queries
    from faultline.tools.spanmetrics import V2

    rules = yaml.safe_load((COMPOSE / "prometheus" / "alert-rules-v2.yml").read_text())
    by_name = {r["alert"]: r["expr"] for g in rules["groups"] for r in g["rules"]}

    assert V2.latency_span_filter, "v2 is expected to narrow which spans count as latency"
    assert V2.latency_span_filter in by_name["ServiceHighLatency"], (
        f"ServiceHighLatency does not carry {V2.latency_span_filter!r}. The capture applies it, so "
        "the summary's latency table would describe a different set of spans from the alerts."
    )
    assert V2.latency_span_filter in metric_queries(V2)["latency-p95"], (
        "the v2 capture does not apply the span filter its alert rule applies"
    )


def test_the_other_two_v2_rules_deliberately_see_every_span() -> None:
    """**The filter is scoped to latency on purpose, and this pins the decision.**

    An error on an internal span is a real failure and should count, and no internal span produced
    a false *error*; the defect was specific to duration. Narrowing `ServiceHighErrorRate` or
    `ServiceNoTraffic` for symmetry would reduce what the benchmark can see in exchange for
    tidiness, so a future change that does it has to come here and argue.
    """
    from faultline.tools.spanmetrics import V2

    rules = yaml.safe_load((COMPOSE / "prometheus" / "alert-rules-v2.yml").read_text())
    by_name = {r["alert"]: r["expr"] for g in rules["groups"] for r in g["rules"]}

    for alert in ("ServiceHighErrorRate", "ServiceNoTraffic"):
        assert "span_kind" not in by_name[alert], (
            f"{alert} has grown a span_kind matcher. Only ServiceHighLatency was measured to need "
            f"one ({V2.latency_span_filter}); an error on an internal span is still an error, and "
            "a service kept alive only by internal spans is still one this benchmark wants to see."
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


def test_kafkas_v2_ceiling_clears_its_committed_heap_with_room_to_grow() -> None:
    """**A freshly restarted kafka must not start above the gate's guard** (2026-09-22).

    v2 ships `-Xms400m` equal to `-Xmx400m`, so the JVM commits 400 MiB at startup and a restart
    re-commits it immediately - v1's recycle remedy measured 92.08% -> 88.81% here against
    99.87% -> 26.27% there. At the shipped 620M ceiling a *fresh* container sat at 88.8% and the
    gate refuses at 90%, so the world was unable to pass its own pre-flight however often it was
    recycled.

    The ceiling has to clear the committed heap plus the measured non-heap peak with enough room
    that the gate's projection does not refuse on the first run.
    """
    limits = yaml.safe_load((COMPOSE / "world-v2.override.yml").read_text())
    memory = limits["services"]["kafka"]["deploy"]["resources"]["limits"]["memory"]
    ceiling_mb = float(memory.rstrip("M"))

    committed_heap_mb = 400.0  # -Xms400m, v2's own setting
    measured_non_heap_peak_mb = 164.0  # 2026-09-22, five hours after a restart

    aged_percent = (committed_heap_mb + measured_non_heap_peak_mb) / ceiling_mb * 100
    assert aged_percent < 70.0, (
        f"kafka's v2 ceiling of {ceiling_mb:.0f}M leaves a five-hour-old container at "
        f"{aged_percent:.1f}%, which gives the gate's 90% guard almost nothing to project into. "
        "The committed heap alone is 400 MiB and a restart cannot reclaim it."
    )


def test_kafkas_consumers_are_named_per_world() -> None:
    """**`sweep` restarts these with `check=False`**, so v1's names on v2 produced
    `No such container` and nothing reported it - the recycle looked like it had happened while
    the consumers were never restarted at all, which is the state T7.27 measured as leaving the
    world quietly broken."""
    from evalharness.rehearse import KAFKA_CONSUMERS_BY_WORLD, kafka_consumers

    assert kafka_consumers("v2") == ("accounting", "fraud-detection", "checkout")
    assert kafka_consumers("v1") == (
        "accounting-service",
        "frauddetection-service",
        "checkout-service",
    )
    assert set(KAFKA_CONSUMERS_BY_WORLD) == {"v1", "v2"}

    # An unknown world gets v1's names, which fail loudly. An empty tuple would make
    # `docker restart` a no-op that reports success - the failure this whole patch is about.
    assert kafka_consumers("v3") == kafka_consumers("v1")


def test_the_recycle_does_not_promise_on_v2_what_it_delivers_on_v1() -> None:
    """The gate printed v1's *"A restart clears this completely"* at v2 operators, recommending a
    remedy measured at three percentage points on a container that starts at 88.8%."""
    from evalharness.rehearse import recycle_effect

    assert "clears this completely" in recycle_effect("v1")
    assert "does NOT clear this" in recycle_effect("v2")
    assert "92.08% -> 88.81%" in recycle_effect("v2"), (
        "the v2 sentence should carry the measurement that falsified v1's remedy, not just deny it"
    )
    assert "no Rosetta" in recycle_effect("v2"), (
        "v2 is native arm64 - measured, 28/28 containers. The text should say Rosetta does not "
        "apply rather than omit it, because a reader arriving from v1's documentation and "
        "ADR-0005 will be looking for exactly that word."
    )


def test_no_v2_overlay_repeats_a_service_key() -> None:
    """**A duplicated mapping key is not an error to PyYAML - it keeps the last one, silently.**

    Caught 2026-09-22 while adding kafka's tmpfs: a second `kafka:` block appended to the end of
    `world-v2.override.yml` parsed cleanly and **dropped the 1024M memory limit** two hundred
    lines above it. `yaml.safe_load` returned a world with the tmpfs and no ceiling, every other
    guard in this file passed, and Compose would have brought that world up. A strict loader is
    the only thing that notices.
    """
    import yaml as _yaml

    class Strict(_yaml.SafeLoader):
        pass

    def no_duplicates(loader: _yaml.SafeLoader, node: _yaml.MappingNode) -> dict:
        seen: set[object] = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node)
            assert key not in seen, f"duplicate key {key!r} - PyYAML would silently keep the last"
            seen.add(key)
        return loader.construct_mapping(node, deep=True)

    Strict.add_constructor(_yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, no_duplicates)

    for name in ("world-v2.override.yml", "telemetry-v2.yml", "otelcol-extras-v2.yml"):
        _yaml.load((COMPOSE / name).read_text(), Loader=Strict)

    for name in ("accounting-bad-credential.yml", "product-catalog-n-plus-one.yml"):
        _yaml.load((REPO_ROOT / "evals" / "attempts" / name).read_text(), Loader=Strict)


def test_kafkas_tmpfs_is_the_size_the_preregistration_says_and_under_its_ceiling() -> None:
    """The disk-fill attempt's whole safety argument is that a filled tmpfs costs kafka's cgroup
    at most its capped size, under the 1024M ceiling. Both numbers live in this file; pin the
    relationship so one cannot be edited without the other."""
    limits = yaml.safe_load((COMPOSE / "world-v2.override.yml").read_text())
    kafka = limits["services"]["kafka"]
    mounts = [
        v for v in kafka.get("volumes", []) if isinstance(v, dict) and v.get("type") == "tmpfs"
    ]

    assert len(mounts) == 1, "kafka should carry exactly one tmpfs: its log directory"
    # `/tmp/kafka-logs`, not the image's documented default: with `KAFKA_*` env configuration the
    # image generates its properties and logs there. A8 (2026-09-23) filled the default path to the
    # byte while kafka wrote elsewhere and nothing paged; the path is read off the running broker.
    assert mounts[0]["target"] == "/tmp/kafka-logs"
    size_mib = mounts[0]["tmpfs"]["size"] / (1024 * 1024)
    ceiling_mib = float(kafka["deploy"]["resources"]["limits"]["memory"].rstrip("M"))

    assert size_mib == 256
    assert 400 + 164 + size_mib < ceiling_mib * 0.9, (
        "committed heap + measured non-heap peak + a full tmpfs must stay under the gate's 90% "
        "guard, or filling the disk on purpose becomes an OOM on purpose"
    )


def test_the_attempt_helpers_need_nothing_newer_than_python_3_9() -> None:
    """**The observation loop must not depend on which `python3` is first on the PATH.**

    A1's first run (2026-09-22 13:46) died before its first poll on `from datetime import UTC`,
    which is 3.11+, because the Mac's system `python3` is 3.9. The attempt was void by the
    protocol's own rule and had to be repeated. The helpers are stdlib-only and are held to 3.9
    here: the syntax by `ast.parse` with a `feature_version`, and the one runtime name that bit
    by walking the imports and attribute accesses rather than grepping - a docstring is allowed
    to say what went wrong.

    Ruff's UP017 will rewrite `timezone.utc` to `UTC` on a 3.12 target, which is how the fix was
    undone once; the helper carries `noqa` for it, and this is the guard behind the `noqa`.
    """
    import ast

    for path in sorted((REPO_ROOT / "evals" / "attempts").glob("*.py")):
        tree = ast.parse(path.read_text(), feature_version=(3, 9))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "datetime":
                names = {alias.name for alias in node.names}
                assert "UTC" not in names, f"{path.name}: datetime.UTC is 3.11+"
            if isinstance(node, ast.Attribute) and node.attr == "UTC":
                base = node.value
                assert not (isinstance(base, ast.Name) and base.id == "datetime"), (
                    f"{path.name}: datetime.UTC is 3.11+"
                )


def test_the_v2_prometheus_config_promotes_the_identifying_resource_attributes() -> None:
    """**A recreated container must not vanish from the rules** (T7.0's A6, 2026-09-23).

    The .NET SDK sets no `service.instance.id`, so with nothing promoted every container that has
    ever run under a service name writes `traces_span_metrics_*` to one series - and the
    spanmetrics connector keeps emitting the dead container's counters, never expiring them, in
    front of the live one's. `docker compose up -d accounting` left a healthy, consuming, exporting
    service reading `0.000 req/s` and `ServiceNoTraffic` firing on it; Tempo had every span. The
    demo's own config promotes `host.name` and `container.name` onto the series for exactly this
    reason (its comment cites the connector's single-writer limitation) and keeps a 30-minute
    out-of-order window; this file replaced the demo's and had dropped both.

    The guard pins the block to what the demo ships rather than to a hand-picked subset, so that
    the file stays a superset of the demo's ingestion settings and not a reinterpretation of them.
    """
    import yaml

    config = yaml.safe_load((COMPOSE / "prometheus" / "prometheus-config-v2.yaml").read_text())

    otlp = config.get("otlp") or {}
    promoted = set(otlp.get("promote_resource_attributes") or [])
    for attribute in ("service.instance.id", "host.name", "container.name", "service.name"):
        assert attribute in promoted, (
            f"prometheus-config-v2.yaml no longer promotes {attribute}: a recreated container "
            "then shares a series with every container before it, and the live one's samples "
            "are refused as duplicates - the service reads 0 req/s while healthy."
        )
    assert otlp.get("keep_identifying_resource_attributes") is True

    window = ((config.get("storage") or {}).get("tsdb") or {}).get("out_of_order_time_window")
    assert window == "30m", (
        "prometheus-config-v2.yaml has lost the demo's 30m out-of-order window; two writers "
        "stamping samples inside one flush need it, or the second is refused as out of order."
    )


def test_the_v2_spanmetrics_connector_keys_resources_on_the_service_not_the_container() -> None:
    """**One service, one counter, one writer - across container recreates** (A6, 2026-09-23).

    By default the spanmetrics connector keys its per-resource metrics on every resource
    attribute, so a container recreated by `compose up -d` (new `container.id`, new
    `process.pid`) is a new resource. The connector never expires the old one and emits it
    first on every flush; Prometheus, which names the series by `service.name` alone on this
    world, keeps the first sample and refuses the live container's. `accounting` consumed,
    wrote and exported every order while reading `0.000 req/s`. Promoting attributes on the
    Prometheus side could not separate the two, because the demo's `resourcedetection`
    processor stamps every resource with the collector host's `host.name`.

    The README's remedy - *"use this in case changing resource attributes (e.g. process id) are
    breaking counter metrics"* - is to key on the service and its SDK. The guard pins that the
    key is set, contains `service.name`, and contains nothing that changes per container.
    """
    import yaml

    extras = yaml.safe_load((COMPOSE / "otelcol-extras-v2.yml").read_text())
    key = (
        (extras.get("connectors") or {})
        .get("spanmetrics", {})
        .get("resource_metrics_key_attributes")
    )

    assert key, (
        "otelcol-extras-v2.yml no longer sets connectors.spanmetrics.resource_metrics_key_"
        "attributes: a recreated container then becomes a second writer to its service's "
        "series and the live one's samples are refused - the service reads 0 req/s while healthy."
    )
    assert "service.name" in key
    per_container = {"container.id", "host.name", "process.pid", "service.instance.id", "host.id"}
    assert not per_container & set(key), (
        f"resource_metrics_key_attributes includes {per_container & set(key)}, which changes "
        "on every recreate and reintroduces the second writer."
    )


def test_the_v2_tempo_has_its_own_config_with_compaction_bounded() -> None:
    """**Tempo on v2 was OOM-killed compacting parquet blocks, twice** (Q91, 2026-09-24).

    35 seconds after a restart, five seconds into its first compaction - four vParquet3 blocks
    merged on a store carrying 45 live and 154 compacted metas - under the same 400M limit v1
    idles at 92-95% of. The parquet writer buffers a 100 MiB row group per output block by
    default; that is the peak. v2 gets its own config file, because v1's `tempo.yaml` is an
    `observability_digest` input and v2's tuning must not orphan v1's bundles, and the config
    bounds the row group and the compacted block. The limit is not raised here: it is measured
    from `container_memory_usage_total{container_name="tempo"}` after the rehearsals.
    """
    import yaml

    tempo = telemetry_v2()["services"]["tempo"]
    mounts = [v for v in tempo["volumes"] if str(v).endswith("/etc/tempo/tempo.yaml:ro")]
    assert mounts == ["../compose/tempo-v2.yaml:/etc/tempo/tempo.yaml:ro"], (
        "v2's Tempo must mount its own config, not v1's tempo.yaml, whose digest v1's bundles carry"
    )
    config = yaml.safe_load((COMPOSE / "tempo-v2.yaml").read_text())
    row_group = config["storage"]["trace"]["block"]["parquet_row_group_size_bytes"]
    assert row_group <= 16 * 1024 * 1024, (
        f"parquet_row_group_size_bytes is {row_group}: the compaction working set is this many "
        "bytes per output block, and 100 MiB (the default) killed Tempo under 400M"
    )
    assert config["compactor"]["compaction"]["max_block_bytes"] <= 512 * 1024 * 1024
    assert config["ingester"]["max_block_duration"] == "30s", "ADR-0037's cut is kept"
    v1 = yaml.safe_load((COMPOSE / "tempo.yaml").read_text())
    assert "block" not in v1["storage"]["trace"], "v1's tempo.yaml is untouched by Q91"


def test_the_v2_tempo_exporter_does_not_back_pressure_the_pipeline() -> None:
    """**A Tempo outage must cost traces, not alerts** (Q93, 2026-09-24).

    With the exporter's defaults, Tempo going down made `otlp/tempo` queue and retry until the
    collector's memory limiter refused every service's spans - `Memory usage is above soft limit.
    Refusing data.`, and `product-catalog` logging `data refused due to high memory usage` - so
    the spanmetrics connector saw nothing and the rules read a quiet world. No retries: a failed
    send is dropped and the receiver keeps accepting.
    """
    import yaml

    extras = yaml.safe_load((COMPOSE / "otelcol-extras-v2.yml").read_text())
    tempo = extras["exporters"]["otlp/tempo"]
    assert tempo.get("retry_on_failure", {}).get("enabled") is False, (
        "otlp/tempo retries again: a Tempo outage will fill its queue, trip the memory limiter "
        "and blind the alert rules"
    )
    assert tempo.get("sending_queue", {}).get("queue_size", 1000) <= 500


def test_the_v2_tempo_receiver_is_not_on_the_collector_port() -> None:
    """**Tempo must not answer on 4317** (Q95, 2026-09-24).

    Every SDK targets `otel-collector:4317` and a gRPC client re-resolves that name only after a
    connection *fails*. Recreating `tempo` with the collector put Tempo on the collector's old
    address, and four services' trace channels reconnected to it and stayed: their spans reached
    Tempo, never the spanmetrics connector, and the rules could not page on them for 2.5 hours.
    On a port no SDK targets, the stale reconnect is refused and the client re-resolves.
    """
    import yaml

    tempo = yaml.safe_load((COMPOSE / "tempo-v2.yaml").read_text())
    endpoint = tempo["distributor"]["receivers"]["otlp"]["protocols"]["grpc"]["endpoint"]
    port = int(endpoint.rsplit(":", 1)[1])
    assert port not in (4317, 4318), (
        f"tempo-v2.yaml's OTLP receiver is on {port}, the port every SDK targets for the "
        "collector: a client reconnecting to a stale address will find Tempo there and stay"
    )
    extras = yaml.safe_load((COMPOSE / "otelcol-extras-v2.yml").read_text())
    assert extras["exporters"]["otlp/tempo"]["endpoint"] == f"tempo:{port}", (
        "otlp/tempo's endpoint must follow tempo-v2.yaml's receiver port"
    )


def test_the_v2_tempo_limit_is_at_least_twice_its_measured_peak() -> None:
    """**Measured on this world, not carried from v1** (Q91, 2026-09-24).

    `container_memory_usage_total_bytes{container_name="tempo"}` over a 51-minute life that ended
    in an OOM kill: idle 150 MiB, sampled peak 374 MiB, a ~220 MiB sawtooth as blocks complete
    and compact. The limit is sized for the peak plus two swings coinciding; this guard pins the
    weaker, exact claim - at least twice the sampled peak - and GOMEMLIMIT under the limit.
    """
    tempo = telemetry_v2()["services"]["tempo"]
    limit_mib = float(tempo["deploy"]["resources"]["limits"]["memory"].rstrip("M"))
    assert limit_mib >= 2 * 374, f"tempo's limit ({limit_mib}M) is under twice the measured peak"
    go_limit = tempo["environment"]["GOMEMLIMIT"]
    assert go_limit.endswith("MiB")
    assert 0.6 * limit_mib <= float(go_limit[:-3]) <= 0.85 * limit_mib, (
        "GOMEMLIMIT should sit at 60-85% of the container limit, so the runtime sees the ceiling "
        "before the kernel does"
    )


def test_the_v2_observability_cover_names_v2s_own_files() -> None:
    """T7.1: a v2 bundle's `observability_digest` covers v2's rules, Prometheus, collector extras
    and Tempo - the files `telemetry-v2.yml` actually mounts - and v1's cover is unchanged, so no
    recorded v1 bundle or run moves."""
    from evalharness import provenance

    v2 = {name for name, _ in provenance.observability_files("v2")}
    assert provenance.observability_files("v1") is provenance.OBSERVABILITY_FILES
    for name in v2:
        if not name.startswith("world-v2/"):  # the clone is gitignored; CI has none
            assert (REPO_ROOT / name).is_file(), f"{name} is under cover but does not exist"
    mounted = set(
        re.findall(r"\.\./(compose/[\w./-]+\.ya?ml):", (COMPOSE / "telemetry-v2.yml").read_text())
    )
    configs = {m for m in mounted if "grafana" not in m}
    assert configs <= v2, f"mounted by telemetry-v2.yml but not under cover: {configs - v2}"
    assert "compose/prometheus/alert-rules-v2.yml" in v2


def test_the_v2_headroom_rows_clear_the_gate_at_their_measured_rest() -> None:
    """T7.1 (2026-09-24): the first v2 bundle's pre-flight refused on accounting, checkout and
    load-generator, and six hours of memory history showed a recycle cannot fix any of them -
    two re-occupy their ceiling within half an hour of a restart and the third is clipped at it.
    Each raised limit must hold its measured figure under the gate's 90 % with room to grow."""
    import yaml

    limits = yaml.safe_load((COMPOSE / "world-v2.override.yml").read_text())["services"]
    measured_mib = {"accounting": 152.0, "checkout": 19.0, "load-generator": 1498.0}
    for service, observed in measured_mib.items():
        memory = limits[service]["deploy"]["resources"]["limits"]["memory"]
        ceiling = float(memory.rstrip("M")) * 1_000_000 / 1_048_576  # M is MB to compose
        assert observed / ceiling < 0.70, (
            f"{service}: {observed} MiB is {observed / ceiling:.0%} of {memory} - too close to "
            "the gate's 90 % to survive the growth the history showed"
        )
    assert limits["load-generator"]["environment"]["LOCUST_USERS"] == 25, (
        "the raise is sized for 25 users; changing the load changes the row's argument"
    )


def test_postgres_on_v2_is_above_the_limit_the_kernel_killed_it_at() -> None:
    """**Q96: the demo's 80M killed Postgres every time the catalog was restored** (2026-09-24).

    The kernel log named it (`Memory cgroup out of memory … (postgres)`, in `postgresql`'s own
    memcg), two kills per unpause, each followed half a second later by a restart. The row that
    raises it is what keeps a freeze's or partition's recovery from carrying a second incident the
    fault did not cause. The test does not say 256M is enough. Only a measured `memory.peak` says
    that, and it is recorded beside the re-record. It says the limit that failed cannot come
    back unnoticed, as kafka's 1024M once silently did (`test_no_v2_overlay_repeats_a_service_key`).
    """
    limits = yaml.safe_load((COMPOSE / "world-v2.override.yml").read_text())
    memory = limits["services"]["postgresql"]["deploy"]["resources"]["limits"]["memory"]
    demo_limit_mb = 80.0  # HostConfig.Memory=83886080 on the demo's own definition
    assert float(memory.rstrip("M")) > demo_limit_mb, (
        f"postgresql's v2 limit is {memory}, at or under the 80M the kernel OOM-killed it at on "
        "every restore of product-catalog (Q96)"
    )


HEADROOM_RULE_HIGHS_MIB = {
    # container: (file, 8-hour one-minute high, MiB), measured 2026-09-24 before the rows landed
    "load-generator": ("world-v2.override.yml", 2974.0),
    "prometheus": ("telemetry-v2.yml", 195.0),
    "otel-collector": ("telemetry-v2.yml", 192.0),
    "opensearch": ("world-v2.override.yml", 945.0),
}


@pytest.mark.parametrize("container", sorted(HEADROOM_RULE_HIGHS_MIB))
def test_the_four_headroom_rows_are_the_rule_applied_to_their_measurement(container: str) -> None:
    """**One rule, stated before two of the four were measured** (`world-v2.override.yml`, last
    block): the new limit is the 8-hour one-minute high / 0.6, rounded up to the next 100M.

    Pinned per container so a later edit to one of these limits is a visible change to the rule's
    output rather than a quiet re-tune. A limit set *below* the rule's figure fails here. One set
    far above it fails too, because the rule is one value and not a floor to raise from.
    """
    import math

    name, high = HEADROOM_RULE_HIGHS_MIB[container]
    limits = yaml.safe_load((COMPOSE / name).read_text())
    memory = limits["services"][container]["deploy"]["resources"]["limits"]["memory"]
    assert float(memory.rstrip("M")) == math.ceil(high / 0.6 / 100) * 100, (
        f"{container}'s limit {memory} is not the headroom rule's figure for its measured high of "
        f"{high:.0f} MiB"
    )
