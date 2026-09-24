"""Re-read a past window from the stores: the alert timeline as `watch.py` would have printed it,
and the world's shape at one instant as `shape.py` would have.

    python3 evals/attempts/replay.py 02:20 02:46            # alerts, 30 s ticks, UTC today
    python3 evals/attempts/replay.py 02:20 02:46 --at 02:36  # plus per-service shape at 02:36

Prometheus keeps `ALERTS{alertstate="firing"}` as a time series, so a window that was watched live
can be read again from the store, tick for tick. That is what this prints: a record from the
store rather than a record from the terminal, which is the honest label when a terminal paste has
been lost - it carries the same clock, from the same source `watch.py` polled. It cannot recover
what the injector printed or what a tool answered at the time; those stay lost and are said so.

Stdlib only and 3.9-safe, for the same reason as the other helpers here (see `watch.py`).
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from paint import dim, green, red

PROM = "http://localhost:9090"
STEP = 30
SHAPE = {
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


def _clock(hhmm: str) -> datetime:
    today = datetime.now(timezone.utc).date()  # noqa: UP017
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime(today.year, today.month, today.day, hour, minute, tzinfo=timezone.utc)  # noqa: UP017


def _get(path: str, params: dict[str, str]) -> list[dict]:
    url = PROM + path + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)["data"]["result"]


def alerts(start: datetime, end: datetime) -> None:
    rows = _get(
        "/api/v1/query_range",
        {
            "query": 'ALERTS{alertstate="firing"}',
            "start": str(int(start.timestamp())),
            "end": str(int(end.timestamp())),
            "step": str(STEP),
        },
    )
    firing: dict[int, set[str]] = {}
    for r in rows:
        name = f"{r['metric'].get('alertname', '?')}/{r['metric'].get('service_name', '?')}"
        for ts, _ in r["values"]:
            firing.setdefault(int(float(ts)), set()).add(name)

    print(f"== ALERTS firing, {start:%H:%M}..{end:%H:%M} UTC, from Prometheus at {STEP} s ==")
    tick = start
    while tick <= end:
        names = sorted(firing.get(int(tick.timestamp()), ()))
        print(f"{tick:%H:%M:%S}  {red(', '.join(names)) if names else green('quiet')}")
        tick += timedelta(seconds=STEP)


def shape(at: datetime) -> None:
    columns: dict[str, dict[str, float]] = {}
    for label, promql in SHAPE.items():
        out: dict[str, float] = {}
        for r in _get("/api/v1/query", {"query": promql, "time": str(int(at.timestamp()))}):
            try:
                out[r["metric"].get("service_name", "?")] = float(r["value"][1])
            except ValueError:  # NaN
                continue
        columns[label] = out
    errors, p95, rate = columns.values()

    print(f"\n== per service, [5m] ending {at:%H:%M} UTC ==")
    print(dim(f"  {'service':<22}  {'err%':>6}  {'p95ms':>7}  {'req/s':>6}"))
    for svc in sorted(set(errors) | set(p95) | set(rate)):
        e = errors.get(svc, float("nan"))
        p = p95.get(svc, float("nan"))
        row = f"  {svc:<22}  {e * 100:6.2f}  {p:7.0f}  {rate.get(svc, 0):6.3f}"
        print(red(row) if e >= 0.05 else row)


def main() -> None:
    argv = sys.argv[1:]
    at = None
    if "--at" in argv:
        index = argv.index("--at")
        at = argv[index + 1] if index + 1 < len(argv) else None
        del argv[index : index + 2]
    if len(argv) != 2 or ("--at" in sys.argv and at is None):
        sys.exit(__doc__)
    start, end = (_clock(a) for a in argv)
    alerts(start, end)
    if at is not None:
        shape(_clock(at))


if __name__ == "__main__":
    main()
