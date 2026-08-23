"""Record a manual scenario rehearsal into a split-labelled artifact bundle (T1.5).

This is not the eval harness. It runs no agent and scores nothing - T4.1 builds that.
What it does is remove the tedium and the inconsistency from rehearsing ten scenarios by
hand: it drives the injector through its CLI, watches Prometheus for the alert, holds
steady state, reverts, and then captures the metric series and timings that the bundle
format (ADR-0009) requires.

The dwell window starts when the alert fires, not when the fault is injected. Detection
latency varies by minutes between fault classes, and counting from injection means the
slowest-alerting faults - the ones whose bundles are most worth having - get the thinnest
steady-state windows.

The one thing it cannot write for you is `incident.md` - the narrative of what a responder
would have seen and concluded. That file is the whole point of the bundle, because it is
what seeds the past-incident store at T2.4b. The script leaves a template with every fact
it knows already filled in.

Usage:
    uv run python -m evalharness.rehearse <scenario-id> [--dwell 300]
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from evalharness.prom import (
    LOKI,
    METRIC_QUERIES,
    POLL_SECONDS,
    QueryError,
    alert_intervals,
    firing_alerts,
    get_json,
    now,
    query_range,
    stamp,
)
from evalharness.provenance import (
    BUNDLE_SCHEMA_VERSION,
    recorder_provenance,
    scenario_fingerprint,
    world_provenance,
)
from evalharness.scenario import Scenario
from injector.world import SERVICE_CONTAINERS

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "evals" / "scenarios"
ARTIFACT_ROOT = SCENARIO_DIR / "artifacts"

STUB_IMAGE = "faultline/ffs-stub:1"
"""The world's flag service (ADR-0006). Its digest is part of what "the same world" means."""


class RehearsalError(RuntimeError):
    """Something went wrong that makes the recorded bundle untrustworthy."""


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


def require_no_active_faults() -> str:
    """Refuse to inject into a world that already has a fault in it.

    The alert baseline gate is not sufficient and cannot be made sufficient. It asks
    whether anything is *firing*, and a fault injected moments earlier has not alerted
    yet - detection takes two to three minutes on this world. Two recorders therefore
    pass each other in that gap: measured, a rehearsal started 99 seconds into another
    fault's run, saw a quiet world, and recorded its own alert timing, alert set and
    metric captures against the other incident's cascade. Every number in that bundle
    belonged to a different fault and nothing in it looked wrong.

    The injector's state file is the authoritative answer and it is true immediately,
    with no detection delay. `evalharness.baseline` has always checked it; the recorder
    did not.
    """
    status = injector("status").strip()
    if not status.startswith("no active injections"):
        raise RehearsalError(
            "aborting before injection: the injector reports a fault already active, so "
            "this world already has an incident in it. A bundle recorded now would time "
            "its own fault against that one.\n"
            f"{status}\n"
            "Wait for it to finish, or `faultline-inject stop --all` if it is stranded."
        )
    return status


def wait_for_clean_baseline(
    timeout_seconds: int, poll: Callable[[], list[str]] | None = None
) -> datetime:
    """Refuse to inject into a world that is already alerting. Returns when it is clean.

    `wait_until` returns the instant its predicate holds, so a rehearsal begun while a
    previous incident is still clearing sees those stale alerts on its very first poll:
    `seconds_to_alert` lands near zero and `alerts_at_fire` names another scenario's
    alerts. Nothing in the resulting bundle looks wrong, which is what makes it dangerous.

    Measured on this world, a `bad_config` fault's alerts keep firing for several minutes
    after the revert - so recording ten scenarios back to back would corrupt every bundle
    after the first. Aborting is the right failure: a bundle nobody can tell is bad is
    worse than a rehearsal that has to be run again.
    """
    poll = poll or firing_alerts
    blocking = poll()
    if not blocking:
        return now()

    print(f"  baseline is not clean: {len(blocking)} alert(s) firing - {', '.join(blocking)}")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        blocking = poll()
        if not blocking:
            print("  baseline clear; injecting")
            return now()
        print(f"  … still waiting on {', '.join(blocking)}", flush=True)

    raise RehearsalError(
        f"aborting before injection: {', '.join(blocking)} still firing after "
        f"{timeout_seconds}s. Injecting now would time this fault's alert against a "
        "previous incident's and record a bundle whose timings are meaningless. Let the "
        "world settle, or raise --baseline-timeout."
    )


# Label names to try first, best guess first. Anything Loki actually reports is tried
# after these, so a promtail config that labels logs some third way still works.
LOG_LABEL_PREFERENCE = ("service", "container", "container_name", "job", "compose_service")

NETWORK_ERRORS = (urllib.error.URLError, QueryError, RehearsalError, TimeoutError, OSError)


@dataclass
class LogSource:
    """A Loki selector discovered by asking Loki, plus what was learned on the way."""

    selector: str | None = None
    label: str | None = None
    values: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def container_for(target: str) -> str:
    """The container name behind a fault target.

    Compose-driven faults name a service (`cartservice`); docker-driven ones already name
    the container (`cart-service`). Logs are labelled by container either way, so the
    service names have to be translated or the selector matches nothing at all.
    """
    return SERVICE_CONTAINERS.get(target, target)


def loki_label_names() -> list[str]:
    payload = get_json(LOKI, "/loki/api/v1/labels", {})
    data = payload.get("data")
    return [v for v in data if isinstance(v, str)] if isinstance(data, list) else []


def loki_label_values(label: str) -> list[str]:
    path = f"/loki/api/v1/label/{urllib.parse.quote(label)}/values"
    payload = get_json(LOKI, path, {})
    data = payload.get("data")
    return sorted(v for v in data if isinstance(v, str)) if isinstance(data, list) else []


def discover_log_source(container: str) -> LogSource:
    """Find a selector that actually matches, by reading Loki's label space.

    The previous version assumed a `container` label and built a regex selector from the
    scenario's target. Both halves were wrong here - promtail labels by `service`, and the
    target is often a compose service name - and the failure was silent: a valid query
    returning zero streams. Asking first costs two HTTP calls and cannot go stale.
    """
    try:
        names = loki_label_names()
    except NETWORK_ERRORS as exc:
        return LogSource(notes=[f"# could not read Loki's label names: {exc}"])

    source = LogSource(notes=[f"# loki labels: {', '.join(names) or '(none)'}"])
    ordered = [n for n in LOG_LABEL_PREFERENCE if n in names]
    ordered += [n for n in names if n not in LOG_LABEL_PREFERENCE]

    for name in ordered:
        try:
            values = loki_label_values(name)
        except NETWORK_ERRORS as exc:
            source.notes.append(f"# {name}: could not read values ({exc})")
            continue
        if container in values:
            source.selector = f'{{{name}="{container}"}}'
            source.label, source.values = name, values
            return source
        near = [v for v in values if container in v or v in container]
        if near:
            source.selector = f'{{{name}="{near[0]}"}}'
            source.label, source.values = name, values
            source.notes.append(
                f"# no exact {name} value for {container!r}; closest is {near[0]!r}"
            )
            return source
        source.notes.append(f"# {name}: no value matching {container!r} ({len(values)} values)")

    source.notes.append(f"# no Loki label carries a value matching {container!r}")
    return source


def loki_logs(container: str, start: datetime, end: datetime, limit: int = 500) -> str:
    """Best effort. Log collection must never invalidate an otherwise good rehearsal.

    When it fails it has to fail legibly: the file records the selector that was tried and
    the label values that exist, so the next person fixes it in one step instead of
    rediscovering Loki's label space by hand.
    """
    source = discover_log_source(container)
    header = [f"# target container: {container}", *source.notes]

    def with_values(reason: str) -> str:
        listing = ", ".join(source.values) if source.values else "(none read)"
        return (
            "\n".join(
                [
                    *header,
                    f"# {reason}",
                    f"# values on {source.label or 'the label tried'}: {listing}",
                    "# fix the selector in evalharness.rehearse, or collect with `docker logs`",
                ]
            )
            + "\n"
        )

    if source.selector is None:
        return with_values("no selector matched - nothing captured")

    header.append(f"# selector: {source.selector}")
    try:
        payload = get_json(
            LOKI,
            "/loki/api/v1/query_range",
            {
                "query": source.selector,
                "start": str(int(start.timestamp() * 1e9)),
                "end": str(int(end.timestamp() * 1e9)),
                "limit": str(limit),
                "direction": "forward",
            },
        )
    except NETWORK_ERRORS as exc:
        return "\n".join([*header, f"# query failed: {exc}", "# collect these by hand"]) + "\n"

    data = payload.get("data")
    streams = data.get("result", []) if isinstance(data, dict) else []
    lines: list[str] = []
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        for entry in stream.get("values", []):
            if isinstance(entry, list) and len(entry) == 2:
                moment = datetime.fromtimestamp(int(entry[0]) / 1e9, tz=UTC)
                lines.append(f"{moment.isoformat(timespec='seconds')}  {entry[1]}")

    if not lines:
        return with_values("selector is valid but matched no lines in this window")
    return "\n".join([*header, f"# {len(lines)} lines", "", *lines]) + "\n"


def find_scenario(scenario_id: str) -> Scenario:
    """Look only at the scored catalog. The examples/ tree illustrates the schema."""
    for path in sorted(SCENARIO_DIR.rglob("*.yaml")):
        if "examples" in path.parts or "artifacts" in path.parts:
            continue
        candidate = Scenario.from_yaml(path)
        if candidate.id == scenario_id:
            return candidate
    raise RehearsalError(f"no scenario with id {scenario_id!r} under {SCENARIO_DIR}")


def offset(moment: str | None, anchor: str | None) -> str:
    """`moment` as a signed offset from `anchor`, e.g. T+2m46s.

    Negative offsets are kept rather than clamped: an alert that started before the fault
    did is a fact about the recording, and "T-1m15s" says so where an absolute timestamp
    would need a reader to subtract.
    """
    if moment is None or anchor is None:
        return "?"
    delta = int((datetime.fromisoformat(moment) - datetime.fromisoformat(anchor)).total_seconds())
    sign = "+" if delta >= 0 else "-"
    minutes, seconds = divmod(abs(delta), 60)
    if minutes and seconds:
        return f"T{sign}{minutes}m{seconds:02d}s"
    return f"T{sign}{minutes}m" if minutes else f"T{sign}{seconds}s"


def duration(seconds: Any) -> str:
    if not isinstance(seconds, int):
        return "?"
    minutes, rest = divmod(seconds, 60)
    if minutes and rest:
        return f"{minutes}m{rest:02d}s"
    return f"{minutes}m" if minutes else f"{rest}s"


def alert_evolution(facts: dict[str, Any]) -> str:
    """How the alert set grew, as lines for the narrative.

    A flat list of what fired at page time understates the incident: run 3 of
    cart-redis-misconfig paged on two services and reached eleven over the next six
    minutes, a seven-service ServiceNoTraffic wave arriving once cart stopped serving
    entirely. Blast radius is what T3.1 scores triage on, so the template has to make the
    growth visible rather than leave it in a JSON file nobody reads while writing.

    Recovery-phase alerts are listed apart from incident alerts. They fired after the fault
    was already removed - they are the recreate's doing, not the fault's - and a narrative
    that folds them in attributes the wrong blast radius.

    Every time here is relative. The page is offset from onset; everything else is offset
    from the page, because that is when the responder started counting. Wall-clock times
    belong in the manifest: a retrieved incident's absolute timestamps carry no information,
    and they are orphaned by every re-record - which has already happened twice.
    """
    at_fire = list(facts.get("alerts_at_fire") or [])
    over_window = list(facts.get("alerts_over_window") or [])
    if not over_window:
        return "_No alerts recorded over the window._"

    onset = facts.get("t_inject")
    page = facts.get("t_alert_firing") or onset
    paged = set(at_fire)
    during = [e for e in over_window if not e.get("began_after_revert")]
    recovery = [e for e in over_window if e.get("began_after_revert")]

    def table(entries: list[dict[str, Any]]) -> list[str]:
        rows = ["| When | Alert | Service | Started | Firing for |", "|---|---|---|---|---|"]
        for e in entries:
            label = f"{e.get('alert')}/{e.get('service')}"
            when = "**on the page**" if label in paged else "later"
            rows.append(
                f"| {when} | {e.get('alert')} | {e.get('service')} | "
                f"{offset(e.get('first_seen'), page)} | {e.get('minutes_firing')}m |"
            )
        return rows

    lines = [
        f"The page went out **{offset(page, onset)}** after onset. Times below are relative",
        "to the page.",
        "",
        *table(during),
    ]
    grew = len(during) - len(at_fire)
    if grew > 0:
        lines += [
            "",
            f"The page named {len(at_fire)} service(s). By the time the fault was removed "
            f"{len(during)} alert(s) had fired - {grew} more than the responder saw when "
            "they started.",
        ]

    if recovery:
        lines += [
            "",
            "#### Fired only after the fix was applied",
            "",
            "<!-- These are the recovery, not the incident: the fault was already gone when",
            "     they started. Recreating a container has its own failure modes. Mention",
            "     them if they mattered to the responder, but do not count them as the",
            "     fault's blast radius. -->",
            "",
            *table(recovery),
        ]
    return "\n".join(lines)


def incident_template(scenario: Scenario, facts: dict[str, Any]) -> str:
    """The narrative the corpus will actually retrieve. Facts pre-filled, judgement left blank."""
    alerts = facts["alerts_at_fire"] or ["(none fired)"]
    over_window = facts.get("alerts_over_window") or []
    during = len([e for e in over_window if not e.get("began_after_revert")])
    recovery = len([e for e in over_window if e.get("began_after_revert")])
    to_page = duration(facts.get("seconds_to_alert"))
    held = duration(facts.get("seconds_of_steady_state"))
    settled = duration(facts.get("seconds_to_settle"))
    return f"""---
origin: scenario:{scenario.id}
split: {scenario.split.value}
fault_class: {scenario.fault_class.value}
onset_to_page: {to_page}
page_to_fix: {held}
fix_to_all_clear: {settled}
---

# {scenario.title}

<!-- NO ABSOLUTE TIMESTAMPS ANYWHERE IN THIS FILE. Write "T+3m" or "about four minutes
     after the page", never "08:02:41". The manifest holds the wall clock; this file is
     read months later as a past incident, where the hour it happened means nothing - and
     a re-record would orphan every timestamp written here. -->

## What was observed

<!-- Write this as the on-call engineer would have experienced it, NOT as someone who
     knew the answer. No mention of the injector. This text is retrieved later as a past
     incident, so an answer written from hindsight teaches the agent to cheat. -->

**On the page:** {", ".join(alerts)}

### How the alert set evolved

<!-- Describe the spread in prose too, not just the table: which service went first, what
     followed it, and how long the gap was. A reader looking this up months later needs
     the shape of the cascade, not only its final size. -->

{alert_evolution(facts)}

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

- Onset to first firing alert: {to_page}
- Services alerting on the page: {len(alerts)}
- Services alerting by the end of the fault: {during}
- Alerts that fired only during recovery: {recovery}
- Steady state held after the page: {held}
- Fix to all-clear: {settled}
- Did the loudest service turn out to be the culprit? <!-- yes / no - this one matters -->
- Would the page alone have led you to the right service? <!-- yes / no -->
"""


def write_bundle(scenario: Scenario, facts: dict[str, Any], out: Path) -> None:
    (out / "metrics").mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(parents=True, exist_ok=True)

    manifest = {
        # Bump obsoletes every earlier bundle - see ADR-0009 before changing anything here.
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "origin": f"scenario:{scenario.id}",
        "scenario_id": scenario.id,
        # T5.3 renders bundles for the demo and needs something human before it has read
        # the scenario file.
        "title": scenario.title,
        "split": scenario.split.value,
        "fault_class": scenario.fault_class.value,
        "injection": scenario.injection.model_dump(mode="json"),
        "expected_remediation_class": scenario.expected_remediation_class.value,
        # Ties the recording to the exact label it was recorded against. If a scenario's
        # scored fields change afterwards, this bundle is evidence for a question that is
        # no longer being asked, and the guards say so instead of scoring it anyway.
        "scenario_fingerprint": scenario_fingerprint(scenario),
        "recorded_by": "evalharness.rehearse",
        "recorder": recorder_provenance("evalharness.rehearse", REPO_ROOT),
        "world": world_provenance(reference_container="cart-service", stub_image=STUB_IMAGE),
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


HAND_WRITTEN = "incident.md"
"""The one file in a bundle a person wrote. A re-record must never be able to destroy it."""


def clear_bundle(out: Path) -> list[str]:
    """Empty a bundle before re-recording into it, keeping only the hand-written narrative.

    `--force` used to write over the top of whatever was already there, which is not the
    same as replacing it: a file the recorder no longer produces simply survived. That is
    how a log capture taken under the old, wrong Loki selector ended up sitting next to the
    correct one, both plausible, nothing in the bundle saying which was current. A stale
    artifact that looks like evidence is worse than a missing one.
    """
    removed: list[str] = []
    for entry in sorted(out.iterdir()):
        if entry.name == HAND_WRITTEN:
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        removed.append(entry.name)
    return removed


def rehearse(
    scenario_id: str, dwell: int, alert_timeout: int, force: bool, baseline_timeout: int = 300
) -> int:
    scenario = find_scenario(scenario_id)
    out = ARTIFACT_ROOT / scenario.split.value / scenario.id
    # Checked now so a doomed run fails in a second rather than in twenty minutes. The
    # old bundle is not touched here: clearing happens after every capture has succeeded,
    # so an interrupted re-record leaves the previous recording intact.
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

    # Two gates, in this order, because they answer different questions. The injector's
    # state file is true the instant a fault is applied; firing alerts lag it by minutes.
    # Checking only the alerts leaves a window in which two recorders each believe they
    # have the world to themselves.
    require_no_active_faults()
    baseline_clear_at = wait_for_clean_baseline(baseline_timeout)

    t_inject = now()
    print(injector("start", fault_id).rstrip())

    t_fire, alerts_at_fire = wait_until(True, alert_timeout, "an alert to fire")

    # Dwell starts at the alert, not at the injection. Counting from injection lets slow
    # detection eat the steady-state window - a fault that took three minutes to alert
    # would leave two minutes of dwell out of five, and the bundle would be thin exactly
    # where the incident was most interesting. If nothing alerted, this is the moment the
    # alert timeout expired, which is the same rule applied to a fault that never fired.
    steady_from = t_fire or now()
    remaining = dwell - int((now() - steady_from).total_seconds())
    if remaining > 0:
        print(f"  holding the fault for {remaining}s of steady state after the alert")
        time.sleep(remaining)

    t_revert = now()
    print(injector("stop", fault_id).rstrip())

    t_clear, _ = wait_until(False, 600, "alerts to clear")

    window_start = t_inject - timedelta(minutes=5)
    window_end = (t_clear or now()) + timedelta(minutes=2)

    # Everything is captured into memory before anything on disk is touched. The previous
    # bundle stays readable until its replacement is fully in hand: a run killed here -
    # which is exactly what happened once - would otherwise have deleted a good recording
    # at minute zero and produced nothing by minute twenty.
    captured: dict[str, dict[str, Any]] = {}
    for name, promql in METRIC_QUERIES.items():
        captured[name] = query_range(promql, window_start, window_end)
        print(f"  captured {name}")

    container = container_for(scenario.injection.target)
    captured_logs = loki_logs(container, window_start, window_end)
    print(f"  captured logs for {container}")

    facts: dict[str, Any] = {
        # Evidence that the world was quiet when this started, rather than an assumption.
        "baseline_clear_at": stamp(baseline_clear_at),
        "t_inject": stamp(t_inject),
        "t_alert_firing": stamp(t_fire),
        "t_revert": stamp(t_revert),
        "t_clear": stamp(t_clear),
        "seconds_to_alert": (None if t_fire is None else int((t_fire - t_inject).total_seconds())),
        # Recorded rather than left to be inferred from timestamps: a thin steady-state
        # window is the difference between a bundle worth seeding the corpus from and one
        # that caught only the transient, and it should be visible in the manifest.
        "seconds_of_steady_state": int((t_revert - steady_from).total_seconds()),
        # How long the world took to go quiet again. T4.1 budgets consecutive runs off
        # this, and it is the number that sets the catalog's cycle time (ADR-0009).
        "seconds_to_settle": (
            None if t_clear is None else int((t_clear - t_revert).total_seconds())
        ),
        # Two different facts, both worth keeping. alerts_at_fire is what a responder saw
        # on the page - the information they actually had when they started. Everything
        # that fired afterwards is the blast radius, which is what T3.1 scores triage on,
        # and a snapshot taken at page time cannot see it.
        "alerts_at_fire": alerts_at_fire,
        # since=t_inject: the window opens five minutes early to show the healthy
        # baseline, and a previous rehearsal still clearing would otherwise have its
        # alerts counted as this incident's blast radius.
        "alerts_over_window": alert_intervals(
            captured["alerts-firing"], step=15, since=t_inject, revert=t_revert
        ),
        "window": {"start": stamp(window_start), "end": stamp(window_end)},
    }

    if out.exists() and any(out.iterdir()):
        removed = clear_bundle(out)
        if removed:
            print(f"  replacing {len(removed)} file(s) from the previous recording")
        if (out / HAND_WRITTEN).exists():
            print(f"  kept {HAND_WRITTEN} - a re-record does not overwrite your writing")

    write_bundle(scenario, facts, out)
    for name, series in captured.items():
        (out / "metrics" / f"{name}.json").write_text(json.dumps(series, indent=2) + "\n")
    (out / "logs" / f"{container}.txt").write_text(captured_logs)
    print(f"  wrote {len(captured)} metric file(s) and logs/{container}.txt")

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
        help=(
            "seconds to hold the fault after the alert fires, or after --alert-timeout "
            "expires if none does (default: 300)"
        ),
    )
    parser.add_argument(
        "--alert-timeout",
        type=int,
        default=420,
        help="seconds to wait for an alert before giving up (default: 420)",
    )
    parser.add_argument(
        "--baseline-timeout",
        type=int,
        default=300,
        help=(
            "seconds to wait for a already-firing alerts to clear before injecting; "
            "aborts rather than recording against a dirty baseline (default: 300)"
        ),
    )
    parser.add_argument("--force", action="store_true", help="overwrite an existing bundle")
    args = parser.parse_args(argv)
    # Line-buffered: these runs are ten minutes long and are almost always watched
    # through a redirect, where block buffering makes a working recorder look hung.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(line_buffering=True)

    try:
        return rehearse(
            args.scenario_id,
            args.dwell,
            args.alert_timeout,
            args.force,
            args.baseline_timeout,
        )
    except RehearsalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
