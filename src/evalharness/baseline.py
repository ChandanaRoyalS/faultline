"""Measure the quiet world: the same four queries, no fault injected (T1.5).

A sibling of evalharness.rehearse rather than a mode of it. The two share their queries
(evalharness.prom) and nothing else: a baseline has no scenario, no split, no injection,
no narrative, and it must not write into a scenario bundle. Folding it in as
`--baseline-only` would have made scenario_id optional, the output path conditional, and
half of rehearse() skippable, which is a lot of branching to save one file.

Why it exists: alert thresholds and every scenario's expected evidence are stated against
"the healthy baseline", and until now that baseline was a handful of point observations.
A rule that says "baseline 0%" is a claim, and claims about this world need an interval.

Usage:
    uv run python -m evalharness.baseline --minutes 45
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from evalharness.prom import (
    METRIC_QUERIES,
    alert_intervals,
    firing_alerts,
    now,
    query_range,
    series_points,
    stamp,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_ROOT = REPO_ROOT / "evals" / "baselines"

ERROR_ALERT_THRESHOLD = 0.05
LATENCY_ALERT_THRESHOLD_MS = 250.0


class BaselineError(RuntimeError):
    """Something makes the measurement untrustworthy as a baseline."""


def active_injections() -> str:
    result = subprocess.run(
        ["faultline-inject", "status"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise BaselineError(f"faultline-inject status failed:\n{result.stdout}{result.stderr}")
    return result.stdout.strip()


def world_is_quiet(status: str) -> bool:
    return status.startswith("no active injections")


def require_quiet_world(when: str) -> str:
    """A baseline recorded over an injected fault measures the fault, not the baseline."""
    status = active_injections()
    if not world_is_quiet(status):
        raise BaselineError(
            f"{when}: the injector reports active faults, so this is not a baseline.\n{status}"
        )
    return status


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile. No numpy in this project, and n is small."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * len(ordered)) - 1))
    return ordered[index]


def summarise(
    points: dict[str, list[tuple[float, float]]], step: int, threshold: float | None
) -> dict[str, dict[str, float]]:
    """mean / min / max / p95 per service, plus minutes spent above `threshold`."""
    out: dict[str, dict[str, float]] = {}
    for service, series in sorted(points.items()):
        values = [v for _, v in series]
        row = {
            "samples": float(len(values)),
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "p95": percentile(values, 0.95),
        }
        if threshold is not None:
            over = sum(1 for v in values if v > threshold)
            row["minutes_over_threshold"] = round(over * step / 60, 1)
            row["fraction_over_threshold"] = over / len(values)
        out[service] = row
    return out


def markdown_table(title: str, rows: dict[str, dict[str, float]], unit: str) -> list[str]:
    if not rows:
        return [f"## {title}", "", "_no series returned_", ""]
    over = "minutes_over_threshold" in next(iter(rows.values()))
    header = f"| Service | mean | min | max | p95 |{' min over threshold |' if over else ''}"
    divider = "|---|---:|---:|---:|---:|" + ("---:|" if over else "")
    lines = [f"## {title}", "", header, divider]

    def fmt(value: float) -> str:
        return f"{value:.2%}" if unit == "ratio" else f"{value:.0f}ms"

    for service, row in sorted(rows.items(), key=lambda kv: -kv[1]["mean"]):
        cells = f"| `{service}` | {fmt(row['mean'])} | {fmt(row['min'])} | {fmt(row['max'])} "
        cells += f"| {fmt(row['p95'])} |"
        if over:
            cells += f" {row['minutes_over_threshold']:.1f} |"
        lines.append(cells)
    lines.append("")
    return lines


def capture(minutes: int, step: int, out_root: Path) -> int:
    require_quiet_world("before measuring")

    start = now()
    out = out_root / start.strftime("%Y%m%dT%H%M%SZ")
    (out / "metrics").mkdir(parents=True, exist_ok=True)
    print(f"measuring the quiet world for {minutes}m -> {out.relative_to(REPO_ROOT)}")
    print(f"  started {stamp(start)}; nothing is being injected")

    deadline = time.monotonic() + minutes * 60
    disturbances: list[dict[str, str | list[str]]] = []
    injections: list[dict[str, str]] = []
    while time.monotonic() < deadline:
        time.sleep(min(60, max(1, deadline - time.monotonic())))
        firing = firing_alerts()
        remaining = max(0, int((deadline - time.monotonic()) / 60))

        # Checked every minute, not only at the start. A fault injected mid-window is
        # invisible to a start-only check, and the resulting summary reads as quiet-world
        # behaviour while actually describing an incident. That happened: a rehearsal ran
        # inside a 45-minute baseline and its alerts were published as the baseline's
        # "alerts that fired on an unfaulted world". One subprocess a minute is cheap
        # against 45 minutes of held world.
        status = active_injections()
        if not world_is_quiet(status):
            injections.append({"at": stamp(now()) or "", "status": status})
            print(f"  [{remaining}m left] !! FAULT INJECTED DURING THE WINDOW", flush=True)

        if firing:
            # Recorded, not fatal. An alert on an unfaulted world is exactly the kind of
            # thing this measurement exists to find.
            disturbances.append({"at": stamp(now()) or "", "alerts": firing})
            print(f"  [{remaining}m left] ALERTS FIRING: {', '.join(firing)}", flush=True)
        elif world_is_quiet(status):
            print(f"  [{remaining}m left] quiet", flush=True)

    end = now()
    status_after = active_injections()
    if not world_is_quiet(status_after):
        injections.append({"at": stamp(end) or "", "status": status_after})
    valid = not injections

    captured: dict[str, dict[str, Any]] = {}
    for name, promql in METRIC_QUERIES.items():
        payload = query_range(promql, start, end, step=step)
        (out / "metrics" / f"{name}.json").write_text(json.dumps(payload, indent=2) + "\n")
        captured[name] = payload
        print(f"  captured metrics/{name}.json")

    errors = summarise(series_points(captured["error-ratio"]), step, ERROR_ALERT_THRESHOLD)
    latency = summarise(series_points(captured["latency-p95"]), step, LATENCY_ALERT_THRESHOLD_MS)
    calls = summarise(series_points(captured["call-rate"]), step, None)
    alert_windows = alert_intervals(captured["alerts-firing"], step)

    manifest = {
        "kind": "baseline",
        # False means the numbers below describe a world something was injected into.
        # They are not a baseline and must not be cited as one.
        "valid": valid,
        "injections_during_window": injections,
        "recorded_by": "evalharness.baseline",
        "window": {"start": stamp(start), "end": stamp(end), "minutes": minutes, "step": step},
        "injector_status": status_after,
        "alerts_during_window": alert_windows,
        "disturbances_observed": disturbances,
        "error_ratio": errors,
        "latency_p95_ms": latency,
        "call_rate": calls,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    invalid_header = [
        "> # ⚠ INVALID — NOT A BASELINE",
        ">",
        "> A fault was injected during this window, so the figures below describe an",
        "> incident, not the quiet world. They must not be cited as baseline behaviour.",
        ">",
        *[f"> - fault active at {i['at']}" for i in injections],
        "",
    ]
    report = [
        *([] if valid else invalid_header),
        f"# Quiet-world baseline — {stamp(start)} to {stamp(end)}"
        + ("" if valid else "  [INVALID]"),
        "",
        f"{minutes} minutes, {step}s step, no fault injected. Load generator running.",
        "",
        *markdown_table(
            f"Error ratio (alert threshold {ERROR_ALERT_THRESHOLD:.0%})", errors, "ratio"
        ),
        *markdown_table(
            f"p95 latency (alert threshold {LATENCY_ALERT_THRESHOLD_MS:.0f}ms)", latency, "ms"
        ),
        "## Alerts that fired on an unfaulted world",
        "",
    ]
    if alert_windows:
        report += ["| Alert | Service | minutes firing | first | last |", "|---|---|---:|---|---|"]
        report += [
            f"| {a['alert']} | {a['service']} | {a['minutes_firing']} | "
            f"{a['first_seen']} | {a['last_seen']} |"
            for a in alert_windows
        ]
    else:
        report.append("None. The world was quiet for the whole window.")
    report += ["", "## Queries", ""]
    for name, promql in METRIC_QUERIES.items():
        report += [f"### {name}", "", "```promql", promql, "```", ""]
    (out / "summary.md").write_text("\n".join(report) + "\n")

    print(f"\nbaseline written to {out.relative_to(REPO_ROOT)}")
    print(f"  summary: {(out / 'summary.md').relative_to(REPO_ROOT)}")
    if not valid:
        # Written anyway: the capture is still useful data, and deleting it would lose
        # the evidence of what interfered. Labelled, and non-zero, so no script treats it
        # as a baseline.
        print(
            f"\n!! INVALID: a fault was active during {len(injections)} check(s) in this "
            "window.\n   The capture is kept and labelled, but it is not a baseline. "
            "Re-run on a quiet world.",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure the world with nothing injected.")
    parser.add_argument("--minutes", type=int, default=45, help="window length (default: 45)")
    parser.add_argument("--step", type=int, default=15, help="query step seconds (default: 15)")
    args = parser.parse_args(argv)
    # Line-buffered: these runs are ten minutes long and are almost always watched
    # through a redirect, where block buffering makes a working recorder look hung.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(line_buffering=True)
    try:
        return capture(args.minutes, args.step, BASELINE_ROOT)
    except BaselineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
