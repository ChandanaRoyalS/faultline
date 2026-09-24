"""The world's shape right now, in the four dimensions the agent's tools can see plus one it cannot.

    python3 evals/attempts/shape.py [TARGET_CONTAINER]

Alerts, per-service error ratio / p95 / call rate over the rules' own [5m] window, every world
container's docker state (the dimension the agent does NOT see - recorded so a distinctness
judgement can say when it leaned on it), and the target's last log lines if a target is given.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
import urllib.request

from paint import dim, green, red, yellow

PROM = "http://localhost:9090"

# The v2 services that emit spans whenever the load generator runs, so each one should have a
# spanmetrics series in every [5m] window the world is up. A running container missing from the
# table is a service the rules cannot page on - measured 2026-09-24 (Q95): four of these sent
# their traces to Tempo's receiver instead of the collector's for 2.5 hours, and R2 ran on a
# world where the freeze's caller could not fire. `kafka` is left out: its spans come only with
# orders and a quiet minute is normal.
INSTRUMENTED = (
    "accounting",
    "ad",
    "cart",
    "checkout",
    "currency",
    "email",
    "flagd",
    "fraud-detection",
    "frontend",
    "frontend-proxy",
    "image-provider",
    "load-generator",
    "payment",
    "product-catalog",
    "product-reviews",
    "quote",
    "recommendation",
    "shipping",
)
QUERIES = {
    "error ratio": (
        "sum by(service_name) "
        '(rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m]))'
        " / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))"
    ),
    "p95 ms": (
        "histogram_quantile(0.95, sum by(service_name, le) "
        '(rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))'
    ),
    "req/s": "sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))",
}


def query(promql: str) -> dict[str, float]:
    url = PROM + "/api/v1/query?" + urllib.parse.urlencode({"query": promql})
    with urllib.request.urlopen(url, timeout=10) as resp:
        rows = json.load(resp)["data"]["result"]
    out: dict[str, float] = {}
    for r in rows:
        try:
            out[r["metric"].get("service_name", "?")] = float(r["value"][1])
        except ValueError:  # NaN
            continue
    return out


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else None

    url = PROM + "/api/v1/query?" + urllib.parse.urlencode({"query": 'ALERTS{alertstate="firing"}'})
    with urllib.request.urlopen(url, timeout=10) as resp:
        rows = json.load(resp)["data"]["result"]
    print("== firing ==")
    for r in rows:
        print(red(f"  {r['metric'].get('alertname', '?')}/{r['metric'].get('service_name', '?')}"))
    if not rows:
        print(green("  none"))

    errors, p95, rate = (query(q) for q in QUERIES.values())
    services = sorted(set(errors) | set(p95) | set(rate))
    print("\n== per service, [5m] ==")
    print(f"  {'service':20s} {'err%':>7s} {'p95ms':>8s} {'req/s':>7s}")
    for s in services:
        e = (errors.get(s) or 0.0) * 100
        p = p95.get(s, 0)
        # The two rules' thresholds, painted at the number so the eye lands where the rule would.
        err_col = red(f"{e:7.2f}") if e >= 5 else f"{e:7.2f}"
        p95_col = red(f"{p:8.0f}") if p >= 250 else f"{p:8.0f}"
        print(f"  {s:20s} {err_col} {p95_col} {rate.get(s, 0):7.3f}")

    ps = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.State}}\t{{.Status}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    running = {line.split("\t")[0] for line in ps.stdout.splitlines() if "\trunning\t" in line}
    silent = sorted(name for name in INSTRUMENTED if name in running and name not in rate)
    print("\n== silent: running, and no span metrics in [5m] ==")
    if silent:
        for name in silent:
            print(red(f"  {name}"))
        print(yellow("  a running service the rules cannot see: the world is not clean (Q95)"))
    else:
        print(green("  none"))

    print("\n== docker state (not agent-visible) ==")
    for line in sorted(ps.stdout.splitlines()):
        name, state, status = [*line.split("\t"), "", ""][:3]
        if state != "running" or "unhealthy" in status or "Paused" in status:
            print(yellow(f"  {name:20s} {state:10s} {status}"))
    print(dim("  (only containers not plainly running are listed)"))

    if target:
        print(f"\n== last 8 log lines: {target} ==")
        logs = subprocess.run(
            ["docker", "logs", "--tail", "8", target], capture_output=True, text=True, check=False
        )
        for line in (logs.stdout + logs.stderr).splitlines()[-8:]:
            print("  " + line[:200])


if __name__ == "__main__":
    main()
