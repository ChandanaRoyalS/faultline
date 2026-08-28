"""T7.3: re-score every stored run's triage under the fixed, per-episode exclusion.

Pure recomputation. No model calls, no live world, no injections - it reads run manifests and
bundle recordings off disk and re-runs `score_triage` on them.

**Each run is scored against the bundle recording that was current when it ran**, not against
whatever the bundle holds now. T7.1 re-recorded all twelve, so scoring an August 26th run
against an August 28th capture would mix this fix with that re-record and measure neither. The
applicable recording is the latest one whose `t_inject` precedes the run, taken from
`superseded/` plus the live manifest.

    uv run python docs/evidence/t7.3-rescore/rescore.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNS = REPO_ROOT / "evals" / "runs"
ARTIFACTS = REPO_ROOT / "evals" / "scenarios" / "artifacts"

sys.path.insert(0, str(REPO_ROOT / "src"))
from evalharness.scoring import score_triage  # noqa: E402


def recordings(scenario: str) -> list[tuple[datetime, dict[str, Any]]]:
    """Every recording of one bundle, oldest first: the archives plus the live manifest."""
    found: list[tuple[datetime, dict[str, Any]]] = []
    for split in ("dev", "holdout"):
        bundle = ARTIFACTS / split / scenario
        if not bundle.is_dir():
            continue
        live = json.loads((bundle / "manifest.json").read_text())
        found.append((datetime.fromisoformat(live["t_inject"]), live))
        archive = bundle / "superseded"
        if archive.is_dir():
            for entry in sorted(archive.iterdir()):
                path = entry / "manifest.json" if entry.is_dir() else entry
                if not path.is_file():
                    continue
                old = json.loads(path.read_text())
                if "t_inject" in old:
                    found.append((datetime.fromisoformat(old["t_inject"]), old))
    return sorted(found, key=lambda row: row[0])


def applicable(scenario: str, when: datetime) -> dict[str, Any] | None:
    """The recording a run at `when` was scored against: the newest one preceding it."""
    prior = [m for stamp, m in recordings(scenario) if stamp <= when]
    return prior[-1] if prior else None


def rescore() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for directory in sorted(RUNS.iterdir()):
        manifest_path = directory / "manifest.json"
        if not directory.is_dir() or not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text())
        score = manifest.get("score")
        if not score:
            continue  # a discarded run was never scored
        started = datetime.fromisoformat(manifest["started_at"])
        truth = applicable(manifest["scenario_id"], started)
        if truth is None:
            continue

        old = score["triage"]
        predicted = set(old["matched"]) | set(old["predicted_not_alerted"])
        new = score_triage(predicted, truth["alerts_over_window"], old["unmeasured_edges_crossed"])

        rows.append(
            {
                "run": directory.name,
                "scenario": manifest["scenario_id"],
                "split": manifest.get("split"),
                "demo": bool(manifest.get("demo")),
                "stamp": score["runtime_version"].rsplit(":", 1)[-1],
                "recording": truth["t_inject"],
                "old_recall": old["recall"],
                "old_precision": old["precision"],
                "new_recall": new.recall,
                "new_precision": new.precision,
                "old_n_alerted": old["n_alerted"],
                "new_n_alerted": len(new.alerted),
                "old_excluded": old["excluded_began_after_revert"],
                "new_excluded": sorted(new.excluded_after_revert),
                "restored": sorted(
                    set(new.alerted)
                    - (set(old["matched"]) | set(old["missed_alerted_not_predicted"]))
                ),
            }
        )
    return rows


def main() -> None:
    rows = rescore()
    moved = [r for r in rows if r["restored"]]
    print(f"{len(rows)} scored runs re-scored; {len(moved)} moved\n")
    if moved:
        print(f"{'run':44}{'restored':22}{'recall':>18}{'precision':>20}")
        for r in moved:
            rec = f"{r['old_recall']:.2f} -> {r['new_recall']:.2f}"
            pre = f"{r['old_precision']:.2f} -> {r['new_precision']:.2f}"
            print(f"{r['run'][:43]:44}{','.join(r['restored']):22}{rec:>18}{pre:>20}")
    (Path(__file__).parent / "rescore.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
