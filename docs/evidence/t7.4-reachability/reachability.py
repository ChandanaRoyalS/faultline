"""T7.4: what evidence each scenario target can produce, read from the re-recorded bundles.

Read-only, and **the live world is not used** - every figure comes from a committed capture, the
committed graph snapshot, or the tool layer's source. That matters for the question being asked:
"can this target produce this evidence" is a property of the recording, and answering it from a
running world would answer it for today rather than for the bundle a narrative was written from.

    uv run python docs/evidence/t7.4-reachability/reachability.py
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from faultline.context.graph import ServiceGraph  # noqa: E402
from injector.world import canonical_service  # noqa: E402

SPAN_CAPTURES = ("call-rate", "error-ratio", "latency-p95")


def populated(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in payload.get("data", {}).get("result", []) if r.get("values")]


def characterise() -> list[dict[str, Any]]:
    nodes = {canonical_service(n) for n in ServiceGraph.from_snapshot().nodes}
    rows: list[dict[str, Any]] = []

    for path in sorted(glob.glob(str(REPO_ROOT / "evals/scenarios/artifacts/*/*/manifest.json"))):
        bundle = Path(path).parent
        manifest = json.loads(Path(path).read_text())
        target = canonical_service(manifest["injection"]["target"])

        runtime = populated(json.loads((bundle / "metrics/runtime.json").read_text()))
        families = sorted({r["metric"].get("__name__", "?") for r in runtime})
        labels = sorted({k for r in runtime for k in r["metric"] if k != "__name__"})

        span = False
        for capture in SPAN_CAPTURES:
            capture_path = bundle / "metrics" / f"{capture}.json"
            if not capture_path.is_file():
                continue
            for series in populated(json.loads(capture_path.read_text())):
                name = series["metric"].get("service_name") or series["metric"].get("exported_job")
                if name and canonical_service(name) == target:
                    span = True

        lines = 0
        for log in sorted((bundle / "logs").glob("*.txt")):
            lines += len(
                [x for x in log.read_text().splitlines() if x.strip() and not x.startswith("#")]
            )

        rows.append(
            {
                "scenario": manifest["scenario_id"],
                "split": manifest["split"],
                "target": target,
                "runtime_series": len(runtime),
                "runtime_families": sorted({f.rsplit("_", 1)[0] for f in families})[:3],
                "runtime_labels": [
                    x for x in labels if x in ("exported_job", "service_name", "job")
                ],
                "span_metrics": span,
                "in_graph": target in nodes,
                "log_lines": lines,
            }
        )
    return rows


def main() -> None:
    rows = characterise()
    header = f"{'scenario':36}{'target':24}{'runtime':>8}{'span':>6}{'graph':>7}{'logs':>7}"
    print(header)
    for row in rows:
        print(
            f"{row['scenario']:36}{row['target']:24}{row['runtime_series']:>8}"
            f"{row['span_metrics']!s:>6}{row['in_graph']!s:>7}{row['log_lines']:>7}"
        )
    blind = [r for r in rows if r["runtime_series"] == 0 and r["log_lines"] < 10]
    print(f"\n{len(blind)} scenario(s) cannot answer 'idle or absent' by any class:")
    for row in blind:
        print(f"  {row['scenario']} -> {row['target']}")
    out = Path(__file__).parent / "reachability.json"
    out.write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
