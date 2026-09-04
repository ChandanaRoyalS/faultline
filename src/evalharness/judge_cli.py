"""`faultline-judge` - score the narratives of runs already on disk (T4.4, T4.2).

No world, no injections, no incidents. The narratives are files; this reads them, compares each
against its scenario's recorded `incident.md`, and writes the judge's answers back into the run
manifest beside the deterministic score.

**Time-to-first-correct-hypothesis is judged here too**, and this is the only place it could be.
It needs a judge, the same lineage rule, and the same reference document - three things this pass
already has - and it must not be a call inside a *scored* run, where it would put judge latency
and judge spend into the figures the run is measuring. One extra model call per run, ~$0.03 at
the rates the budget records.

**It degrades rather than fails.** A run whose trajectory is not in the database - an archived
tree, a different machine, a run predating the table - records why it could not be measured and
the judging continues. An unmeasurable metric must not cost a pass its agreement figures.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


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
    p.add_argument(
        "--no-first-correct",
        action="store_true",
        help=(
            "skip T4.2's time-to-first-correct-hypothesis. It is one extra model call per run "
            "(~$0.03) and needs the trajectory in Postgres; on by default because a metric "
            "nothing invokes is not a metric"
        ),
    )
    p.add_argument("--postgres-dsn", default=None, help="where the trajectories are")
    return p


NOT_MEASURED = "not measured"
"""What a run records when first-correct could not be computed. **A stated absence, not a
missing key** - ADR-0019's rule that empty is evidence and errored is not, applied to a metric:
a run with no trajectory in reach and a run where the pipeline never held the right idea are
different facts, and a missing field would read as the second."""


def _first_correct(
    model: object, settings: object, loaded: dict[str, Any], *, dsn: str | None
) -> dict[str, Any]:
    """T4.2's index, or a recorded reason it could not be taken.

    Every failure here is caught and written down. The judging pass's own product is the
    agreement figures; losing all of them because one trajectory was unreachable would be a
    metric taking its host down with it.
    """
    from evalharness.first_correct import hypotheses, judge_first_correct, steps_for

    trajectory_id = (loaded["manifest"].get("score") or {}).get("trajectory_id")
    if not trajectory_id:
        return {"measured": False, "why": f"{NOT_MEASURED}: the run recorded no trajectory id"}
    try:
        if dsn is None:
            from faultline.context.settings import ContextSettings

            dsn = ContextSettings().postgres_dsn
        items = hypotheses(steps_for(dsn, str(trajectory_id)))
    except Exception as unreachable:  # a database that is not there is not a scoring failure
        return {"measured": False, "why": f"{NOT_MEASURED}: {type(unreachable).__name__}"}
    if not items:
        # **Empty is evidence.** A trajectory that made no claim at all is a real outcome - a run
        # gated before fan-out has exactly this shape - and it is not the same as a failure.
        return {"measured": True, "index": -1, "why": "the trajectory holds no hypothesis"}
    try:
        found = judge_first_correct(
            model,
            settings,
            scenario_id=loaded["scenario_id"],
            run_id=loaded["run_id"],
            agent_model=loaded["agent_model"],
            items=items,
        )
    except Exception as failure:
        return {"measured": False, "why": f"{NOT_MEASURED}: {type(failure).__name__}"}
    return {"measured": True, **found.as_dict()}


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
    # `load_run` drops demo runs, so the default sweep never judges one. Naming a demo run
    # explicitly still works: the rule is that no *aggregate* counts it, not that it may
    # never be looked at (T5.3).
    runs = [
        loaded
        for directory in sorted(root.iterdir())
        if directory.is_dir() and (not wanted or directory.name in wanted)
        if (loaded := load_run(directory, allow_demo=bool(wanted))) is not None
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
        if not args.no_first_correct:
            loaded["manifest"]["first_correct"] = _first_correct(
                model, settings, loaded, dsn=args.postgres_dsn
            )
        loaded["manifest_path"].write_text(
            json.dumps(loaded["manifest"], indent=2, default=str) + "\n"
        )

    # **The generation each judged run belongs to** (T7.55). Observed from the run's own freeze
    # manifest where it has one, reconstructed from its timestamp where it predates T7.55 - and
    # `judged_rows` never puts two worlds in one table.
    from evalharness.generations import generation_of

    gens = {loaded["run_id"]: generation_of(loaded["manifest"]) for loaded in runs}
    table = "\n".join(judged_rows(results, gens))
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
