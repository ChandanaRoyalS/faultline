"""Dev sweep 3 against dev sweep 4, on every endpoint T4.12 registered in advance.

Emits the per-scenario table in `evals/runs/SWEEP-2026-08-27-evidence.md`, including the column
that turned out to explain the result: dispatches at the service whose failure *is* the fault.

`TARGET` is hard-coded because it is ground truth about each scenario. Inferring it from a
trajectory would read the answer off a run that may have localized wrongly - which is the thing
being measured.

    uv run python docs/evidence/t4.12-evidence/s4compare.py /tmp/s4.json

Read-only: no model call, no injection, no write to the store.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import psycopg

from faultline.context.settings import ContextSettings

S3 = [
    "20260826T191342Z-ad-memory-squeeze",
    "20260826T193515Z-cart-bad-image-tag",
    "20260826T195646Z-cart-dependency-latency",
    "20260826T185202Z-cart-redis-misconfig",
    "20260826T201433Z-frauddetection-memory-squeeze",
    "20260826T203657Z-product-catalog-flag-failure",
    "20260826T205707Z-shipping-wrong-image",
]
S4 = [
    "20260827T064846Z-ad-memory-squeeze",
    "20260827T071009Z-cart-bad-image-tag",
    "20260827T073004Z-cart-dependency-latency",
    "20260827T074754Z-cart-redis-misconfig",
    "20260827T080802Z-frauddetection-memory-squeeze",
    "20260827T083025Z-product-catalog-flag-failure",
    "20260827T090637Z-shipping-wrong-image",
]

TARGET = {
    "ad-memory-squeeze": "adservice",
    "cart-bad-image-tag": "cartservice",
    "cart-dependency-latency": "cartservice",
    "cart-redis-misconfig": "cartservice",
    "frauddetection-memory-squeeze": "frauddetectionservice",
    "product-catalog-flag-failure": "productcatalogservice",
    "shipping-wrong-image": "shippingservice",
}


def row(cur: Any, run_id: str) -> dict[str, Any]:
    manifest = json.loads(Path(f"evals/runs/{run_id}/manifest.json").read_text())
    score = manifest["score"]
    cur.execute(
        "SELECT tool, request, envelope FROM trajectory_tool_calls "
        "WHERE trajectory_id=%s ORDER BY seq",
        (score["trajectory_id"],),
    )
    calls = cur.fetchall()

    silent: set[tuple[str, str]] = set()
    reissues = 0
    for tool, request, envelope in calls:
        key = (tool, (request or {}).get("service", "?"))
        if key in silent:
            reissues += 1
        if 'empty="true"' in envelope.split("\n")[0]:
            silent.add(key)

    scenario = score["scenario_id"]
    services = [(request or {}).get("service") for _, request, _ in calls]
    judge = manifest.get("judge") or {}
    return {
        "scenario": scenario,
        "stamp": score["runtime_version"].rsplit(":", 1)[-1],
        "returned": score["fault_class"]["returned"],
        "correct": score["fault_class"]["correct"],
        "abstained": score["fault_class"]["abstained"],
        "calls": len(calls),
        "silent_streams": len(silent),
        "reissues": reissues,
        "tools": sorted({tool for tool, _, _ in calls}),
        "target_dispatches": sum(1 for s in services if s == TARGET[scenario]),
        "distinct_services": len({s for s in services if s}),
        "judge": judge.get("root_cause_agreement"),
    }


def verdict(entry: dict[str, Any]) -> str:
    if entry["abstained"]:
        return "ABST"
    return entry["returned"] + (" ok" if entry["correct"] else " WRONG")


def main() -> None:
    with psycopg.connect(ContextSettings().postgres_dsn) as conn, conn.cursor() as cur:
        a = {r["scenario"]: r for r in (row(cur, x) for x in S3)}
        b = {r["scenario"]: r for r in (row(cur, x) for x in S4)}

    print(f"{'scenario':32} {'S3':>22} {'S4':>22} | target  svcs  reissue  silent")
    for name in sorted(a):
        x, y = a[name], b[name]
        print(
            f"{name:32} {verdict(x):>22} {verdict(y):>22} | "
            f"{x['target_dispatches']}->{y['target_dispatches']}  "
            f"{x['distinct_services']}->{y['distinct_services']}  "
            f"{x['reissues']}->{y['reissues']}  "
            f"{x['silent_streams']}->{y['silent_streams']}"
        )

    print()
    for tag, sweep in (("S3", a), ("S4", b)):
        answered = [r for r in sweep.values() if not r["abstained"]]
        print(
            f"{tag}: coverage {len(answered)}/7  "
            f"correct-of-answered {sum(1 for r in answered if r['correct'])}/{len(answered)}  "
            f"re-issues {sum(r['reissues'] for r in sweep.values())} "
            f"in {sum(1 for r in sweep.values() if r['reissues'])} runs  "
            f"judge same {sum(1 for r in sweep.values() if r['judge'] == 'same_mechanism')}  "
            f"trace_query {sum(1 for r in sweep.values() if 'trace_query' in r['tools'])}/7  "
            f"tool calls {sum(r['calls'] for r in sweep.values())}"
        )

    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps({"s3": a, "s4": b}, indent=1))


if __name__ == "__main__":
    main()
