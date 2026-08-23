"""Record a manual scenario rehearsal into a split-labelled artifact bundle (T1.5).

This is not the eval harness. It runs no agent and scores nothing - T4.1 builds that.
What it does is remove the tedium and the inconsistency from rehearsing ten scenarios by
hand: it drives the injector through its CLI, watches Prometheus for the alert, waits out
a steady-state window, reverts, and then captures the metric series and timings that the
bundle format (ADR-0009) requires.

The one thing it cannot write for you is `incident.md` - the narrative of what a responder
would have seen and concluded. That file is the whole point of the bundle, because it is
what seeds the past-incident store at T2.4b. The script leaves a template with every fact
it knows already filled in.

Usage:
    uv run python -m evalharness.rehearse <scenario-id> [--dwell 300]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from evalharness.scenario import Scenario

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "evals" / "scenarios"
ARTIFACT_ROOT = SCENARIO_DIR / "artifacts"

PROMETHEUS = "http://localhost:9090"
LOKI = "http://localhost:3100"

POLL_SECONDS = 15
HTTP_TIMEOUT = 20

# Captured over the full incident window. Keys become filenames under metrics/.
METRIC_QUERIES: dict[str, str] = {
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


class RehearsalError(RuntimeError):
    """Something went wrong that makes the recorded bundle untrustworthy."""


def now() -> datetime:
    return datetime.now(UTC)


def stamp(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat(timespec="seconds")


def get_json(base: str, path: str, params: dict[str, str]) -> dict[str, Any]:
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as response:
        payload: Any = json.loads(response.read().decode())
    if not isinstance(payload, dict):
        raise RehearsalError(f"{url} did not return a JSON object")
    return payload


def firing_alerts() -> list[str]:
    """Alert names currently firing, in the order Prometheus reports them."""
    payload = get_json(PROMETHEUS, "/api/v1/alerts", {})
    data = payload.get("data")
    alerts = data.get("alerts", []) if isinstance(data, dict) else []
    names: list[str] = []
    for alert in alerts:
        if not isinstance(alert, dict) or alert.get("state") != "firing":
            continue
        labels = alert.get("labels", {})
        name = labels.get("alertname") if isinstance(labels, dict) else None
        service = labels.get("service_name") if isinstance(labels, dict) else None
        if isinstance(name, str):
            names.append(f"{name}/{service}" if isinstance(service, str) else name)
    return names


def injector(*args: str) -> str:
    """Drive the injector through its public CLI, never its internals."""
    result = subprocess.run(
        ["faultline-inject", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RehearsalError(
            f"faultline-inject {' '.join(args)} failed:\n{result.stdout}{result.stderr}"
        )
    return result.stdout


def wait_until(
    predicate_true: bool, timeout_seconds: int, label: str
) -> tuple[datetime | None, list[str]]:
    """Poll firing alerts until the count is (non-)empty as required, or time out."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        names = firing_alerts()
        if bool(names) is predicate_true:
            return now(), names
        print(f"  … waiting for {label} ({len(names)} firing)", flush=True)
        time.sleep(POLL_SECONDS)
    print(f"  ! timed out waiting for {label}", flush=True)
    return None, firing_alerts()


def query_range(query: str, start: datetime, end: datetime, step: int = 15) -> dict[str, Any]:
    return get_json(
        PROMETHEUS,
        "/api/v1/query_range",
        {
            "query": query,
            "start": str(int(start.timestamp())),
            "end": str(int(end.timestamp())),
            "step": str(step),
        },
    )


def loki_logs(selector: str, start: datetime, end: datetime, limit: int = 500) -> str:
    """Best effort. Log collection must never invalidate an otherwise good rehearsal."""
    try:
        payload = get_json(
            LOKI,
            "/loki/api/v1/query_range",
            {
                "query": selector,
                "start": str(int(start.timestamp() * 1e9)),
                "end": str(int(end.timestamp() * 1e9)),
                "limit": str(limit),
                "direction": "forward",
            },
        )
    except (urllib.error.URLError, RehearsalError, TimeoutError) as exc:
        return f"# log collection failed for {selector}: {exc}\n# collect these by hand\n"

    data = payload.get("data")
    streams = data.get("result", []) if isinstance(data, dict) else []
    lines: list[str] = [f"# selector: {selector}"]
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        for entry in stream.get("values", []):
            if isinstance(entry, list) and len(entry) == 2:
                moment = datetime.fromtimestamp(int(entry[0]) / 1e9, tz=UTC)
                lines.append(f"{moment.isoformat(timespec='seconds')}  {entry[1]}")
    if len(lines) == 1:
        lines.append("# no lines matched - widen the selector or collect by hand")
    return "\n".join(lines) + "\n"


def find_scenario(scenario_id: str) -> Scenario:
    """Look only at the scored catalog. The examples/ tree illustrates the schema."""
    for path in sorted(SCENARIO_DIR.rglob("*.yaml")):
        if "examples" in path.parts or "artifacts" in path.parts:
            continue
        candidate = Scenario.from_yaml(path)
        if candidate.id == scenario_id:
            return candidate
    raise RehearsalError(f"no scenario with id {scenario_id!r} under {SCENARIO_DIR}")


def incident_template(scenario: Scenario, facts: dict[str, Any]) -> str:
    """The narrative the corpus will actually retrieve. Facts pre-filled, judgement left blank."""
    alerts = facts["alerts_at_fire"] or ["(none fired)"]
    return f"""---
origin: scenario:{scenario.id}
split: {scenario.split.value}
fault_class: {scenario.fault_class.value}
injected_at: {facts["t_inject"]}
resolved_at: {facts["t_clear"]}
---

# {scenario.title}

## What was observed

<!-- Write this as the on-call engineer would have experienced it, NOT as someone who
     knew the answer. No mention of the injector. This text is retrieved later as a past
     incident, so an answer written from hindsight teaches the agent to cheat. -->

Alerts that fired: {", ".join(alerts)}

## What was checked

<!-- The signals a responder would reach for, in order, including the ones that turned
     out to be dead ends. Dead ends are valuable - they are what distinguishes a real
     investigation from a lookup. -->

## Root cause

<!-- One paragraph, plain language. -->

## Resolution

<!-- What fixed it, and what class of fix that is: rollback / restart / config_revert /
     scale. Must match the scenario's expected_remediation_class. -->

## Detection notes

- Time from fault to first firing alert: {facts["seconds_to_alert"]}s
- Services that alerted: {len(alerts)}
- Did the loudest service turn out to be the culprit? <!-- yes / no - this one matters -->
"""


def write_bundle(scenario: Scenario, facts: dict[str, Any], out: Path) -> None:
    (out / "metrics").mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(parents=True, exist_ok=True)

    manifest = {
        "origin": f"scenario:{scenario.id}",
        "scenario_id": scenario.id,
        "split": scenario.split.value,
        "fault_class": scenario.fault_class.value,
        "injection": scenario.injection.model_dump(),
        "expected_remediation_class": scenario.expected_remediation_class.value,
        "recorded_by": "evalharness.rehearse",
        **facts,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    queries = ["# Exact queries behind every file in metrics/. Re-runnable.", ""]
    for name, promql in METRIC_QUERIES.items():
        queries += [f"## {name}", "", "```promql", promql, "```", ""]
    (out / "queries.md").write_text("\n".join(queries))

    incident = out / "incident.md"
    if incident.exists():
        print(f"  keeping existing {incident.name} - not overwriting your writing")
    else:
        incident.write_text(incident_template(scenario, facts))


def rehearse(scenario_id: str, dwell: int, alert_timeout: int, force: bool) -> int:
    scenario = find_scenario(scenario_id)
    out = ARTIFACT_ROOT / scenario.split.value / scenario.id
    if out.exists() and any(out.iterdir()) and not force:
        raise RehearsalError(
            f"{out.relative_to(REPO_ROOT)} already has contents. Pass --force to re-record."
        )

    fault_id = scenario.injection.method
    if fault_id not in injector("list"):
        raise RehearsalError(
            f"{fault_id!r} is not a known injector fault. The scenario's injection.method "
            "must name a fault from `faultline-inject list`."
        )

    print(f"rehearsing {scenario.id}  [{scenario.split.value}]  fault={fault_id}")

    t_inject = now()
    print(injector("start", fault_id).rstrip())

    t_fire, alerts_at_fire = wait_until(True, alert_timeout, "an alert to fire")

    remaining = dwell - int((now() - t_inject).total_seconds())
    if remaining > 0:
        print(f"  holding the fault for {remaining}s of steady state")
        time.sleep(remaining)

    t_revert = now()
    print(injector("stop", fault_id).rstrip())

    t_clear, _ = wait_until(False, 600, "alerts to clear")

    window_start = t_inject - timedelta(minutes=5)
    window_end = (t_clear or now()) + timedelta(minutes=2)

    facts: dict[str, Any] = {
        "t_inject": stamp(t_inject),
        "t_alert_firing": stamp(t_fire),
        "t_revert": stamp(t_revert),
        "t_clear": stamp(t_clear),
        "seconds_to_alert": (None if t_fire is None else int((t_fire - t_inject).total_seconds())),
        "alerts_at_fire": alerts_at_fire,
        "window": {"start": stamp(window_start), "end": stamp(window_end)},
    }

    write_bundle(scenario, facts, out)

    for name, promql in METRIC_QUERIES.items():
        series = query_range(promql, window_start, window_end)
        (out / "metrics" / f"{name}.json").write_text(json.dumps(series, indent=2) + "\n")
        print(f"  captured metrics/{name}.json")

    target = scenario.injection.target
    selector = f'{{container=~".*{target}.*"}}'
    (out / "logs" / f"{target}.txt").write_text(loki_logs(selector, window_start, window_end))
    print(f"  captured logs/{target}.txt")

    if t_fire is None:
        print("\n!! no alert fired. Investigate before trusting this bundle.")
    print(f"\nbundle written to {out.relative_to(REPO_ROOT)}")
    print("next: write incident.md, then set `rehearsed: true` in the scenario YAML.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record a manual scenario rehearsal into its split-labelled bundle."
    )
    parser.add_argument("scenario_id")
    parser.add_argument(
        "--dwell",
        type=int,
        default=300,
        help="seconds to hold the fault before reverting (default: 300)",
    )
    parser.add_argument(
        "--alert-timeout",
        type=int,
        default=420,
        help="seconds to wait for an alert before giving up (default: 420)",
    )
    parser.add_argument("--force", action="store_true", help="overwrite an existing bundle")
    args = parser.parse_args(argv)

    try:
        return rehearse(args.scenario_id, args.dwell, args.alert_timeout, args.force)
    except RehearsalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
