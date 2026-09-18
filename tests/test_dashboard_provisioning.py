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
ALLOWED_PATHS = {"/api/health", "/api/dashboards/db"}
PINNED_DATASOURCE_UID = "webstore-metrics"
PINNED_DATASOURCES = {"prometheus": PINNED_DATASOURCE_UID, "loki": "loki", "tempo": "tempo"}
"""One uid per datasource type, each provisioned as a file: the demo's Prometheus, and this
repository's Loki (T1.2) and Tempo (T6.1) datasource files. A panel pointing anywhere else is
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
    urls = {s for s in _string_constants(source) if s.startswith("http")}
    assert urls <= ALLOWED_BASES, f"unexpected host: {urls - ALLOWED_BASES}"


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
            assert panel["datasource"]["uid"] == PINNED_DATASOURCES[kind], panel["title"]
            for target in panel["targets"]:
                assert target["datasource"] == panel["datasource"], panel["title"]


def test_the_pinned_uids_are_the_ones_the_datasource_files_provision() -> None:
    """The dashboard names `loki` and `tempo`; the files under `compose/` are where those uids
    are set. A rename on either side leaves a blank panel, so the two are held together here."""
    for name, uid in (("loki", "loki"), ("tempo", "tempo")):
        text = (REPO_ROOT / "compose" / f"grafana-{name}-datasource.yml").read_text()
        assert f"uid: {uid}" in text, name
        assert PINNED_DATASOURCES[name] == uid


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


def test_the_self_dashboard_says_why_its_prometheus_panels_may_be_empty() -> None:
    """Nothing scrapes `/metrics` until Q73 lands, because the scrape job is digest-locked. A
    dashboard that was blank without saying why would read as broken; this one says so on the
    screen, and names the row."""
    dashboard = json.loads(SELF_DASHBOARD.read_text())
    notes = [p for p in dashboard["panels"] if p["type"] == "text"]

    assert notes and "Q73" in notes[0]["options"]["content"]
    assert "observability_digest" in notes[0]["options"]["content"]


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
