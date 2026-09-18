"""The dashboard path must stay narrow enough that it cannot route around the digest.

T1.2's dashboard is pushed over Grafana's HTTP API rather than mounted through
`compose/telemetry.yml`, because that file feeds `compose_digest` and a panel cannot move
anything the harness measures (ADR-0030). The obvious objection to that decision is that an
escape hatch which exists gets used: once there is a script that changes the running world
outside the provenance envelope, the next change goes through it too.

These tests are the answer to that objection. They pin the script to Grafana's dashboard
API on localhost, and they fail if it ever grows the ability to write a file, run a command,
or touch a file the world digests cover.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from injector.settings import InjectorSettings

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "provision_dashboards.py"
DASHBOARDS = sorted((REPO_ROOT / "compose" / "dashboards").glob("*.json"))
SELF_DASHBOARD = REPO_ROOT / "compose" / "dashboards" / "faultline-self.json"

ALLOWED_BASES = {"http://localhost:3000/grafana", "http://localhost:3000"}
DATASOURCE_URLS = {"http://host.docker.internal:9091"}
"""A URL the script *posts to Grafana* as the self-metrics datasource's address (Q73). The script
never contacts it; Grafana does. Named here so that the host test below stays a test of what the
script talks to, and so that a second such value is a decision rather than a drift."""
ALLOWED_PATHS = {"/api/health", "/api/dashboards/db", "/api/datasources", "/api/datasources/uid/"}
"""Health, dashboards - and since T6.6 / Q73 one datasource, read by uid and created or updated.
**Widened by exactly one resource, on purpose, and this set is where that decision is held**: the
next path added here is the moment ADR-0030's guard is being routed around rather than extended,
and the person adding it should be able to say why in the ADR's next addendum."""
PINNED_DATASOURCE_UID = "webstore-metrics"
SELF_METRICS_UID = "faultline-self-metrics"
PINNED_DATASOURCES = {
    "prometheus": {PINNED_DATASOURCE_UID, SELF_METRICS_UID},
    "loki": {"loki"},
    "tempo": {"tempo"},
}
"""The uids a panel may point at, per datasource type: the demo's Prometheus (`webstore-metrics`),
this repository's Loki (T1.2) and Tempo (T6.1) datasource files, and the platform's own
Prometheus, pushed over the API by the script under test (Q73). A panel pointing anywhere else is
blank. `text` panels have no datasource and are exempt."""


def _string_constants(source: str) -> set[str]:
    return {
        node.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


@pytest.fixture(scope="module")
def source() -> str:
    return SCRIPT.read_text()


def test_the_script_talks_only_to_grafana_on_localhost(source: str) -> None:
    """Every URL literal is a Grafana base the script requests, except the one datasource address
    it hands to Grafana - and that one must be built into a request body, never requested."""
    urls = {s for s in _string_constants(source) if s.startswith(("http://", "https://"))}
    assert urls <= ALLOWED_BASES | DATASOURCE_URLS, f"unexpected host: {urls - ALLOWED_BASES}"
    tree = ast.parse(source)
    requested = {
        node.args[0].id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", "") == "Request"
        and node.args
        and isinstance(node.args[0], ast.Name)
    }
    assert requested and "url" in requested and "SELF_METRICS_URL" not in requested


def test_the_only_api_paths_are_health_and_dashboards(source: str) -> None:
    paths = {s for s in _string_constants(source) if s.startswith("/api/")}
    assert paths == ALLOWED_PATHS, f"API surface changed: {paths}"


def test_the_script_cannot_run_a_command(source: str) -> None:
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "subprocess" not in imported
    assert "os" not in imported


def test_the_script_cannot_write_a_file(source: str) -> None:
    calls = {
        node.func.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    for forbidden in ("write_text", "write_bytes", "mkdir", "unlink", "rename"):
        assert forbidden not in calls, f"the dashboard path must not {forbidden}"
    assert "open" not in _string_constants(source)


def _docstrings(tree: ast.AST) -> set[str]:
    """Prose may name the file the code must not touch."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                found.add(doc)
    return found


def test_the_script_never_names_a_file_the_world_digest_covers(source: str) -> None:
    """The point of ADR-0030 is that this path changes nothing a bundle records.

    Docstrings are excluded deliberately. This test failed on its first run against the
    script's own docstring, which exists to explain why it does *not* mount through
    `telemetry.yml` - the explanation names the file, and should. What must never appear is
    a digest-covered filename in code the script executes.
    """
    code = _string_constants(source) - _docstrings(ast.parse(source))
    covered = {Path(name).name for name in InjectorSettings().compose_files}
    for name in covered:
        for literal in code:
            assert name not in literal, f"{name} is a compose_digest input; code must not name it"


def test_every_dashboard_is_valid_json_with_an_identity() -> None:
    assert DASHBOARDS, "no dashboards to provision"
    for path in DASHBOARDS:
        dashboard = json.loads(path.read_text())
        assert dashboard.get("uid"), f"{path.name} has no uid, so it cannot be overwritten"
        assert dashboard.get("title")
        assert dashboard.get("panels")


def test_every_panel_uses_a_pinned_datasource_of_its_own_type() -> None:
    """The demo provisions Prometheus at a fixed uid, and T6.6's self dashboard adds one Loki and
    one Tempo panel at the uids this repository's own datasource files pin. A panel pointing
    anywhere else is blank. Until T6.6 every panel was Prometheus and the assertion said so."""
    for path in DASHBOARDS:
        for panel in json.loads(path.read_text())["panels"]:
            if panel["type"] == "text":
                assert "datasource" not in panel and "targets" not in panel, panel["title"]
                continue
            kind = panel["datasource"]["type"]
            assert panel["datasource"]["uid"] in PINNED_DATASOURCES[kind], panel["title"]
            for target in panel["targets"]:
                assert target["datasource"] == panel["datasource"], panel["title"]


def test_the_pinned_uids_are_the_ones_the_datasource_files_provision() -> None:
    """The dashboard names `loki` and `tempo`; the files under `compose/` are where those uids
    are set. A rename on either side leaves a blank panel, so the two are held together here."""
    for name, uid in (("loki", "loki"), ("tempo", "tempo")):
        text = (REPO_ROOT / "compose" / f"grafana-{name}-datasource.yml").read_text()
        assert f"uid: {uid}" in text, name
        assert PINNED_DATASOURCES[name] == {uid}


def test_the_self_dashboard_shows_what_metrics_exposes_and_nothing_else() -> None:
    """**Piece 5 reads piece 3.** Every `faultline_` series a panel queries is one `/metrics`
    serves, spelled from `observability.metrics.NAMESPACE`; a panel over a series that does not
    exist is blank, and a series nobody shows is a scrape for nothing."""
    import re

    from faultline.observability import metrics

    exposed = {
        f"{metrics.NAMESPACE}_{suffix}"
        for suffix in (
            "incidents_queued",
            "investigations_active",
            "investigations_total",
            "investigation_seconds_bucket",
            "model_tokens_total",
            "model_usd_total",
        )
    }
    dashboard = json.loads(SELF_DASHBOARD.read_text())
    queried = {
        name
        for panel in dashboard["panels"]
        if panel.get("datasource", {}).get("type") == "prometheus"
        for target in panel["targets"]
        for name in re.findall(rf"{metrics.NAMESPACE}_[a-z_]+", target["expr"])
    }

    assert queried == exposed, f"missing: {exposed - queried}, unknown: {queried - exposed}"


def test_the_self_dashboard_reads_the_platform_s_prometheus_and_not_the_world_s() -> None:
    """**Q73's decision, held.** The world's Prometheus is inside `observability_digest`, its
    target set is a measurement, and the agent queries it; the platform's counters must not be
    there. Every Prometheus panel on this dashboard reads the datasource the script pushes, and
    the note panel says where the numbers come from rather than why they might be missing."""
    dashboard = json.loads(SELF_DASHBOARD.read_text())
    prometheus_panels = [
        p for p in dashboard["panels"] if p.get("datasource", {}).get("type") == "prometheus"
    ]
    notes = [p for p in dashboard["panels"] if p["type"] == "text"]

    assert prometheus_panels
    assert all(p["datasource"]["uid"] == SELF_METRICS_UID for p in prometheus_panels)
    assert notes and "prometheus-self" in notes[0]["options"]["content"]
    assert "not the world's" in notes[0]["options"]["content"]


def test_the_script_pushes_the_datasource_the_dashboard_names(source: str) -> None:
    """Two spellings of one uid, held equal: the script creates `faultline-self-metrics` and the
    dashboard's panels read it. Rename either alone and every Prometheus panel goes blank."""
    namespace: dict[str, object] = {}
    exec(  # the module's constants, without running main()
        compile(
            "\n".join(
                line for line in source.splitlines() if line.startswith("SELF_METRICS_UID = ")
            ),
            "provision_dashboards",
            "exec",
        ),
        namespace,
    )

    assert namespace["SELF_METRICS_UID"] == SELF_METRICS_UID
    assert "isDefault" in source and '"isDefault": False' in source, (
        "the demo's own Prometheus stays what Explore opens by default"
    )


def test_the_self_prometheus_config_is_outside_the_world_digest_and_says_so() -> None:
    """The file exists so that the world's config need not change; if it ever joined
    `OBSERVABILITY_FILES` the reason for it would be void. Both copies scrape one job, the
    same job, and differ only in the target - the Alertmanager shape (deploy/README §3.4)."""
    import yaml

    from evalharness import provenance

    dev = yaml.safe_load((REPO_ROOT / "compose" / "prometheus" / "self.yaml").read_text())
    vm = yaml.safe_load((REPO_ROOT / "deploy" / "prometheus-self.yaml").read_text())
    hashed = {name for name, _ in provenance.OBSERVABILITY_FILES}

    assert "compose/prometheus/self.yaml" not in hashed
    assert [j["job_name"] for j in dev["scrape_configs"]] == ["faultline"]
    assert dev["scrape_configs"][0]["static_configs"][0]["targets"] == ["host.docker.internal:8000"]
    assert vm["scrape_configs"][0]["static_configs"][0]["targets"] == ["faultline:8000"]
    vm["scrape_configs"][0]["static_configs"][0]["targets"] = dev["scrape_configs"][0][
        "static_configs"
    ][0]["targets"]
    assert vm == dev, "the two copies may differ in the target and nothing else"


def test_the_loki_datasource_links_trace_ids_to_the_tempo_uid() -> None:
    """Piece 4 puts `trace_id` on the line; this is the half that makes it a link. The regex
    reads the JSON field, not free text, and the target is the uid `grafana-tempo-datasource.yml`
    pins - which `test_the_pinned_uids_are_the_ones_the_datasource_files_provision` guards."""
    import re

    text = (REPO_ROOT / "compose" / "grafana-loki-datasource.yml").read_text()

    assert "derivedFields" in text
    assert "datasourceUid: tempo" in text
    match = re.search(r"matcherRegex: '(.+)'", text)
    assert match
    pattern = match.group(1)
    trace_id = "e420efea2fe46357cc202aaf0a53802e"
    line = f'{{"ts": "t", "msg": "m", "trace_id": "{trace_id}", "span_id": "a1"}}'
    found = re.search(pattern, line)
    assert found and found.group(1) == trace_id
    assert "$${__value.raw}" in text, "a single $ is expanded by Grafana's provisioning and lost"


def test_the_dashboard_stays_tied_to_the_alert_rules() -> None:
    """Its whole purpose is that a firing alert is explicable on the same screen."""
    titles = " ".join(
        panel["title"] for path in DASHBOARDS for panel in json.loads(path.read_text())["panels"]
    )
    for rule in ("ServiceHighErrorRate", "ServiceHighLatency", "ServiceNoTraffic"):
        assert rule in titles, f"no panel names {rule}"
