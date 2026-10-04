"""Read-only: is the v2 world in its defined state before a recording or a scored run?

Run from the repository, with the world up:
    python3 scripts/world_check.py
    python3 scripts/world_check.py --landing checkout     (before an injection recording)

**This is the world check every v2 recording since 2026-09-27 ran as `~/Downloads/world_check.py`**,
brought into the repository unchanged in what it checks (the headline run's Addendum 1, item 1),
with two checks added that a scored run needs and a recording did not:

- **Alertmanager running and ready, and its receiver answering (Q124).** It routes Prometheus's
  alerts to Faultline's ingest webhook. It had been stopped since 2026-09-28 and nothing looked,
  because a recording reads Prometheus's `ALERTS` and never needed it. A scored run does: no alert,
  no incident. The receiver half (the ingest's `/healthz` on port 8000) was added by the build's
  part D: the registration names it, and part A had checked Alertmanager alone.
- **quote's clock (Q121).** quote's spans drift into the past each time the Mac sleeps (one reading
  was 36 hours). Every order trace carries them, and `trace_query` orders traces by their start.
  This fails when any quote server span sits more than a second from the call that made it.

The checks that were already there: Loki and Tempo answer /ready with 200 and promtail is running
(Q115); Tempo's search finds traces in a minute twenty minutes back, so it reaches its stored
blocks and not only the ingester (Q120); cart's store-command client spans at about two a second
over ten minutes, the state the catalog was recorded in (Q116); no container but grafana at or over
85 % of its memory limit; nothing firing; kafka running, its log directory writable by the broker's
user and under 50 % used (Q114). With --landing SERVICE, also that the service's Loki stream holds
no line at all in the last 35 minutes (Q117).

It writes nothing and changes nothing. Stdlib only. Exit status 0 when every check passes, 1 when
any fails, so a batch runner can gate on it.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

PROM = "http://localhost:9090"
TEMPO = "http://localhost:3200"
LOKI = "http://localhost:3100"
ALERTMANAGER = "http://localhost:9093"
RECEIVER = "http://localhost:8000"
"""Alertmanager's configured receiver: `compose/prometheus/alertmanager.yml` posts to
`host.docker.internal:8000/api/v1/alerts`, which is Faultline's ingest on the host. Its log until
2026-09-28 is every delivery refused at that port (`docs/evidence/t7.3/alertmanager/`)."""

QUOTE_MAX_OFFSET_SECONDS = 1.0
"""Q121's bound, the owner's decision of 2026-10-04: a quote server span more than a second from
its caller's span is a clock that has drifted, not a slow call (quote answers in milliseconds)."""

CHECKS: list[bool] = []


def check(name: str, ok: bool, detail: str) -> None:
    CHECKS.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name:<44} {detail}")


def status(url: str) -> int | str:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return int(r.status)
    except urllib.error.HTTPError as e:
        return int(e.code)
    except Exception as e:
        return repr(e)


def get_json(url: str, timeout: int = 30) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def prom(q: str) -> list[dict[str, Any]]:
    url = PROM + "/api/v1/query?" + urllib.parse.urlencode({"query": q})
    result: list[dict[str, Any]] = get_json(url, timeout=10)["data"]["result"]
    return result


def sh(*cmd: str) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


def _attr(attrs: list[dict[str, Any]] | None, key: str) -> str:
    for a in attrs or []:
        if a.get("key") == key:
            return str(next(iter((a.get("value") or {}).values()), ""))
    return ""


def trace_spans(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """Every span of one Tempo trace as `{service, id, parent, start}`, start in seconds."""
    out = []
    for batch in trace.get("batches") or trace.get("resourceSpans") or []:
        service = _attr((batch.get("resource") or {}).get("attributes"), "service.name")
        for scope in batch.get("scopeSpans") or []:
            for span in scope.get("spans") or []:
                out.append(
                    {
                        "service": service,
                        "id": span.get("spanId"),
                        "parent": span.get("parentSpanId") or "",
                        "start": int(span.get("startTimeUnixNano") or 0) / 1e9,
                    }
                )
    return out


def quote_offsets(spans: list[dict[str, Any]]) -> list[float]:
    """For each quote span whose parent is another service's span, how far apart they start.

    **The caller's span is the clock that is right**: Q121 measured every other service's spans
    agreeing with the Docker VM's clock to the second, and quote's alone off. A quote span called
    from shipping starts within milliseconds of shipping's client span when quote's clock is right.
    """
    by_id = {s["id"]: s for s in spans if s["id"]}
    offsets = []
    for s in spans:
        parent = by_id.get(s["parent"])
        if s["service"] == "quote" and parent is not None and parent["service"] != "quote":
            offsets.append(abs(s["start"] - parent["start"]))
    return offsets


def check_quote_clock() -> None:
    now = time.time()
    params = {
        "q": '{resource.service.name="quote"}',
        "start": str(int(now - 15 * 60)),
        "end": str(int(now - 60)),
        "limit": "10",
    }
    try:
        found = get_json(TEMPO + "/api/search?" + urllib.parse.urlencode(params)).get("traces")
        offsets: list[float] = []
        for t in found or []:
            offsets += quote_offsets(trace_spans(get_json(f"{TEMPO}/api/traces/{t['traceID']}")))
    except Exception as e:
        check("quote's clock within 1 s (Q121)", False, repr(e))
        return
    if not offsets:
        check("quote's clock within 1 s (Q121)", False, "no quote span with a caller in 15 min")
        return
    worst = max(offsets)
    check(
        "quote's clock within 1 s (Q121)",
        worst <= QUOTE_MAX_OFFSET_SECONDS,
        f"worst offset {worst:.3f} s over {len(offsets)} span(s); a restart of quote resets it",
    )


def main() -> int:
    for name, url in (("loki", f"{LOKI}/ready"), ("tempo", f"{TEMPO}/ready")):
        s = status(url)
        check(f"{name} /ready", s == 200, str(s))
    st = sh("docker", "inspect", "-f", "{{.State.Status}}", "promtail")
    check("promtail running", st == "running", st)

    # Q124: the alert path a scored run opens its incident through.
    am = sh("docker", "inspect", "-f", "{{.State.Status}}", "alertmanager")
    ready = status(f"{ALERTMANAGER}/-/ready")
    check(
        "alertmanager running and ready (Q124)",
        am == "running" and ready == 200,
        f"{am}, /-/ready {ready}",
    )
    receiver = status(f"{RECEIVER}/healthz")
    check(
        "alertmanager's receiver answering (Q124)", receiver == 200, f"ingest /healthz {receiver}"
    )

    # Q120: /ready says nothing about search. A one-minute search twenty minutes back reaches only
    # stored blocks.
    now = time.time()
    params = {
        "q": "{}",
        "start": str(int(now - 21 * 60)),
        "end": str(int(now - 20 * 60)),
        "limit": "20",
    }
    try:
        found = len(
            get_json(TEMPO + "/api/search?" + urllib.parse.urlencode(params)).get("traces") or []
        )
        check(
            "tempo search reaches stored blocks (Q120)",
            found > 0,
            f"{found} trace(s) in the minute 20 min ago",
        )
    except Exception as e:
        check("tempo search reaches stored blocks (Q120)", False, repr(e))

    check_quote_clock()

    r = prom(
        'sum(rate(traces_span_metrics_calls_total{service_name="cart", '
        'span_kind="SPAN_KIND_CLIENT"}[10m]))'
    )
    v = float(r[0]["value"][1]) if r else 0.0
    check(
        "cart store-command spans (Q116)", 1.5 <= v <= 3.5, f"{v:.2f}/s over 10m (defined: about 2)"
    )

    high = []
    for line in sh(
        "docker", "stats", "--no-stream", "--format", "{{.Name}} {{.MemPerc}}"
    ).splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].endswith("%"):
            pct = float(parts[1].rstrip("%"))
            if pct >= 85 and parts[0] != "grafana":
                high.append(f"{parts[0]} {pct:.1f}%")
    check("no container but grafana >= 85 % memory", not high, ", ".join(high) or "none")

    firing = [
        a["metric"].get("alertname", "?")
        + "/"
        + a["metric"].get("service_name", a["metric"].get("service", "?"))
        for a in prom('ALERTS{alertstate="firing"}')
    ]
    check("nothing firing", not firing, ", ".join(firing) or "none")

    ks = sh(
        "docker",
        "inspect",
        "-f",
        "{{.State.Status}} restarts={{.RestartCount}} started={{.State.StartedAt}}",
        "kafka",
    )
    check("kafka running (Q114)", ks.startswith("running"), ks)
    df = sh("docker", "exec", "kafka", "df", "--output=pcent", "/tmp/kafka-logs").splitlines()[-1]
    df = df.strip()
    pct = int(df.rstrip("%")) if df.rstrip("%").isdigit() else 100
    check("kafka tmpfs under 50 % used", pct < 50, df)
    w = sh(
        "docker",
        "exec",
        "kafka",
        "sh",
        "-c",
        "test -w /tmp/kafka-logs && echo writable || echo NOT writable",
    )
    check("kafka log directory writable by the broker's user", w == "writable", w)

    if "--landing" in sys.argv:
        svc = sys.argv[sys.argv.index("--landing") + 1]
        now = time.time()
        params = {
            "query": f'{{service="{svc}"}}',
            "start": str(int((now - 35 * 60) * 1e9)),
            "end": str(int(now * 1e9)),
            "limit": "50",
            "direction": "backward",
        }
        res = get_json(
            LOKI + "/loki/api/v1/query_range?" + urllib.parse.urlencode(params), timeout=10
        )["data"]["result"]
        got = sorted((int(ts), line) for st in res for ts, line in st["values"])
        newest = ""
        if got:
            age = int(now - got[-1][0] / 1e9)
            wait = max(0, (35 * 60 - age + 59) // 60)
            newest = f"newest {age} s ago ({wait} more minutes to wait): {got[-1][1][:120]}"
        check(
            f"{svc} stream empty for 35 min (Q117)",
            not got,
            f"{len(got)} line(s)" + (f"; {newest}" if newest else ""),
        )

    print()
    failed = CHECKS.count(False)
    print("ALL PASS" if not failed else f"NOT READY - {failed} check(s) failed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
