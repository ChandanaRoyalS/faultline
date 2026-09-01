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

ALLOWED_BASES = {"http://localhost:3000/grafana", "http://localhost:3000"}
ALLOWED_PATHS = {"/api/health", "/api/dashboards/db"}
PINNED_DATASOURCE_UID = "webstore-metrics"


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


def test_every_panel_uses_the_pinned_prometheus_datasource() -> None:
    """The demo provisions Prometheus at a fixed uid; a panel pointing anywhere else is blank."""
    for path in DASHBOARDS:
        for panel in json.loads(path.read_text())["panels"]:
            assert panel["datasource"]["uid"] == PINNED_DATASOURCE_UID, panel["title"]
            for target in panel["targets"]:
                assert target["datasource"]["uid"] == PINNED_DATASOURCE_UID, panel["title"]


def test_the_dashboard_stays_tied_to_the_alert_rules() -> None:
    """Its whole purpose is that a firing alert is explicable on the same screen."""
    titles = " ".join(
        panel["title"] for path in DASHBOARDS for panel in json.loads(path.read_text())["panels"]
    )
    for rule in ("ServiceHighErrorRate", "ServiceHighLatency", "ServiceNoTraffic"):
        assert rule in titles, f"no panel names {rule}"
