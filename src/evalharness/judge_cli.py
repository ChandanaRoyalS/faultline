"""`faultline-judge` - score the narratives of runs already on disk (T4.4).

No world, no injections, no incidents. The narratives are files; this reads them, compares each
against its scenario's recorded `incident.md`, and writes the judge's answers back into the run
manifest beside the deterministic score.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="faultline-judge",
        description=(
            "Judge the narratives of scored runs against their recorded incident.md "
            "(T4.4, ADR-0022 §1.3). Reads FAULTLINE_JUDGE_MODEL; there is no default."
        ),
        epilog=(
            "Exit codes: 0 judged; 3 refused - no judge model set, or the judge shares a "
            "tuning lineage with the agent under test and the violation was not opted into."
        ),
    )
    p.add_argument("run_ids", nargs="*", help="run directory names; default: every scored run")
    p.add_argument("--runs-root", default=None)
    p.add_argument("--out", default=None, metavar="FILE", help="write the judged table here")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="check configuration and lineage, list what would be judged, and make no model call",
    )
    return p


def run(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)

    from evalharness.judge import (
        RUN_ROOT,
        JudgeModel,
        JudgeSettings,
        JudgeUnconfiguredError,
        LineageViolationError,
        judge_run,
        judged_rows,
        load_run,
        require_lineage,
    )

    settings = JudgeSettings.from_env()
    root = Path(args.runs_root) if args.runs_root else RUN_ROOT
    wanted = set(args.run_ids)
    runs = [
        loaded
        for directory in sorted(root.iterdir())
        if directory.is_dir() and (not wanted or directory.name in wanted)
        if (loaded := load_run(directory)) is not None
    ]
    if not runs:
        print("no scored runs to judge")
        return 0

    try:
        model_id = settings.require_model()
        shared, why = require_lineage(runs[0]["agent_model"], settings)
    except (JudgeUnconfiguredError, LineageViolationError) as refusal:
        print(f"REFUSED: {refusal}")
        return 3

    print(f"judge {model_id}   agent {runs[0]['agent_model']}")
    print(
        f"lineage: {'SHARED - every figure carries the violation' if shared else 'clear'} ({why})"
    )
    print(f"{len(runs)} scored run(s) to judge")
    if args.dry_run:
        for loaded in runs:
            state = "REFUSED NARRATIVE" if loaded["narrative_refused"] else "would judge"
            print(f"  {loaded['scenario_id']:32} {state}")
        return 0

    model = JudgeModel(model_id)
    results = []
    for loaded in runs:
        result = judge_run(
            model,
            settings,
            scenario_id=loaded["scenario_id"],
            run_id=loaded["run_id"],
            agent_model=loaded["agent_model"],
            agent_narrative=loaded["narrative"],
            narrative_refused=loaded["narrative_refused"],
        )
        results.append(result)
        verdict = result.agreement if result.scored else f"NOT JUDGED ({result.not_scored_because})"
        print(f"  {result.scenario_id:32} {verdict}")
        loaded["manifest"]["judge"] = result.as_dict()
        loaded["manifest_path"].write_text(
            json.dumps(loaded["manifest"], indent=2, default=str) + "\n"
        )

    table = "\n".join(judged_rows(results))
    print("\n" + table)
    tin = sum(r.tokens_in for r in results)
    tout = sum(r.tokens_out for r in results)
    print(f"\nJUDGE COST  in {tin} / out {tout} tokens   ${tin / 1e6 * 5 + tout / 1e6 * 25:.4f}")
    if args.out:
        Path(args.out).write_text(table + "\n")
        print(f"wrote {args.out}")
    return 0


def run_cli() -> None:  # pragma: no cover - console entry point
    sys.exit(run())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
