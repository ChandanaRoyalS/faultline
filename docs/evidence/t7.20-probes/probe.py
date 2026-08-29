"""T7.20 alerting probe: inject, watch the one open gate, revert, confirm recovery.

    uv run python docs/evidence/t7.20-probes/probe.py <fault-id> <B|C> <attempt> <minutes>

Records nothing to the catalog and runs no agent. `B` watches cart-service's container state and
.NET runtime counters; `C` watches error ratios along the checkout path.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs" / "evidence" / "t7.20-probes"
PROM = "http://localhost:9090/api/v1"
KNOWN_TAIL = {"checkoutservice", "frontend", "loadgenerator"}
WATCHED = ("shippingservice", "checkoutservice", "frontend", "quoteservice")


def sh(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    r = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    return r.returncode, (r.stdout + r.stderr).strip()


def ts() -> str:
    return datetime.now(UTC).strftime("%H:%M:%SZ")


def prom(query: str) -> dict[str, float]:
    url = f"{PROM}/query?" + urllib.parse.urlencode({"query": query})
    try:
        rows = json.load(urllib.request.urlopen(url, timeout=10))["data"]["result"]
    except Exception:
        return {}
    return {r["metric"].get("service_name", "?"): float(r["value"][1]) for r in rows}


def firing() -> list[str]:
    try:
        alerts = json.load(urllib.request.urlopen(f"{PROM}/alerts", timeout=10))["data"]["alerts"]
    except Exception:
        return ["?"]
    return sorted(
        f"{a['labels'].get('alertname', '')}/{a['labels'].get('service_name', '')}"
        for a in alerts
        if a["state"] == "firing"
    )


def gate(target: str) -> tuple[str, bool]:
    """T7.17's scoped relaxation, reused and stated: proceed only when every refusal is the
    characterised at-rest excursion (ADR-0025) on services other than the one being measured."""
    _, out = sh(
        [
            "uv",
            "run",
            "python",
            "-c",
            "import json; from evalharness import gate; r = gate.read(); "
            "print(json.dumps({'passed': r.passed, 'refusals': r.refusals, "
            "'over': list(r.p95_over_ceiling), 'alerts': r.firing_alerts}))",
        ],
        cwd=ROOT,
    )
    try:
        g = json.loads(out.splitlines()[-1])
    except Exception:
        return "unreadable", False
    if g["passed"]:
        return "PASS", True
    over = set(g["over"])
    alerts = {a.split("/")[-1] for a in g["alerts"]}
    unrelated = [
        w
        for w in g["refusals"]
        if not w.startswith(("note:", "p95 above")) and "alert(s) firing" not in w
    ]
    ok = bool(
        all(a.startswith("ServiceHighLatency/") for a in g["alerts"])
        and over
        and over <= KNOWN_TAIL
        and alerts <= KNOWN_TAIL
        and target not in over
        and target not in alerts
        and not unrelated
    )
    return ("RELAXED|" if ok else "REFUSED|") + "; ".join(g["refusals"])[:150], ok


def one(values: dict[str, float]) -> float | None:
    return next(iter(values.values()), None)


def cart_state() -> dict[str, object]:
    fmt = "{{.State.Status}}|{{.State.OOMKilled}}|{{.RestartCount}}|{{.HostConfig.Memory}}"
    _, inspect = sh(["docker", "inspect", "cart-service", "--format", fmt])
    _, usage = sh(
        ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}|{{.MemPerc}}", "cart-service"]
    )
    p95 = prom("histogram_quantile(0.95, sum by(service_name,le) (rate(latency_bucket[2m])))")
    return {
        "inspect": inspect,
        "stats": usage,
        "heap_bytes": one(prom('process_runtime_dotnet_gc_heap_size{exported_job="cartservice"}')),
        "gc_collections": one(
            prom('sum(process_runtime_dotnet_gc_collections_count{exported_job="cartservice"})')
        ),
        # B1's confound: frontend and loadgenerator carry at-rest excursions, so an alert on
        # them is ambiguous. cartservice does not, so its own error rate and p95 attribute.
        "errors": err_rates(),
        "cart_p95_ms": p95.get("cartservice"),
        "frontend_p95_ms": p95.get("frontend"),
    }


def err_rates() -> dict[str, str]:
    errors = prom('sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m]))')
    total = prom("sum by(service_name) (rate(calls_total[2m]))")
    out = {}
    for service in WATCHED:
        rate, bad = total.get(service, 0.0), errors.get(service, 0.0)
        out[service] = f"{bad:.3f}/{rate:.3f} = {(bad / rate * 100 if rate else 0):.1f}%"
    return out


def main() -> None:
    fault, kind, attempt, minutes = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    snapshot = cart_state if kind == "B" else err_rates
    record: dict[str, object] = {"probe": kind, "attempt": attempt, "fault": fault, "started": ts()}
    print(f"=== probe {kind}{attempt} · {fault} · {ts()} ===", flush=True)

    record["gate"], ok = gate("cartservice" if kind == "B" else "shippingservice")
    print(f"  gate: {str(record['gate'])[:120]}", flush=True)
    if not ok:
        record["outcome"] = "not attempted - gate refused"
        print("  REFUSED - not injecting", flush=True)
        dump(record, kind, attempt)
        return

    record["before"] = snapshot()
    before_alerts = firing()
    record["alerts_before"] = before_alerts
    print(f"  before: {record['before']}", flush=True)

    code, _ = sh(["uv", "run", "faultline-inject", "start", fault], cwd=ROOT)
    record["inject_rc"] = code
    started = time.time()
    print(f"  injected rc={code} @ {ts()}", flush=True)

    timeline: list[dict[str, object]] = []
    fired_at: int | None = None
    for _ in range(minutes):
        time.sleep(60)
        elapsed = int(time.time() - started)
        snap: dict[str, object] = {"t": f"T+{elapsed}s", "alerts": firing()}
        snap.update(snapshot() if kind == "B" else {"errors": err_rates()})
        new = [a for a in snap["alerts"] if a not in before_alerts]  # type: ignore[operator]
        snap["new_alerts"] = new
        if new and fired_at is None:
            fired_at = elapsed
            record["first_alert_seconds"] = elapsed
            record["first_alerts"] = new
        timeline.append(snap)
        print(
            f"  T+{elapsed:4}s new={new or '-'} | {snap.get('inspect') or snap.get('errors')}",
            flush=True,
        )
    record["timeline"] = timeline

    if kind == "C":
        _, logs = sh(["docker", "logs", "checkout-service", "--tail", "8"])
        record["checkout_logs_under_fault"] = logs.splitlines()

    record["fired"] = fired_at is not None
    print(f"  --- reverting @ {ts()} · fired={record['fired']} ---", flush=True)
    code, out = sh(["uv", "run", "faultline-inject", "stop", fault], cwd=ROOT)
    record["revert_rc"], record["revert_out"] = code, out[-160:]
    time.sleep(45)
    record["after"] = snapshot()
    record["alerts_after"] = firing()
    record["finished"] = ts()
    print(f"  after: {record['after']}\n  alerts after: {record['alerts_after']}", flush=True)
    dump(record, kind, attempt)


def dump(record: dict[str, object], kind: str, attempt: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{kind}{attempt}.json").write_text(json.dumps(record, indent=1) + "\n")


if __name__ == "__main__":
    main()
