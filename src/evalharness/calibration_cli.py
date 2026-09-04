"""`faultline-calibrate` — grade the judge, one run at a time, blind (T4.2).

Three flags, in the order they are used:

    faultline-calibrate --next                       # shows one run, WITHOUT the judge's verdict
    faultline-calibrate --grade <run_id> \\
        --level same_mechanism --reason "..."        # records, THEN reveals the judge's
    faultline-calibrate --report                     # raw agreement, Cohen's kappa, and the reading

**Flags rather than a prompt loop**, and not for convenience. A grading session driven by
interactive input leaves no record of what the grader was shown, and the one property this whole
exercise depends on is that they were not shown the judge's answer. Here `--next` prints exactly
what it prints, and it is the same in a transcript as it was on the day.

`--grade` refuses a run that already has a standing blind grade. Revising after the reveal is
`--regrade`, which writes a second record marked not-blind and is excluded from the figure - see
`calibration.regrade`.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="faultline-calibrate",
        description=(
            "Grade the judge's root-cause verdicts against your own, blind (T4.2). The judge's "
            "answer is revealed only after your grade is on disk - a grade made after seeing it "
            "measures confirmation, not agreement."
        ),
        epilog=(
            "The pool excludes abstentions - a run that returned fault_class:unknown made no "
            "claim, and the judge grades every abstention `different` by construction. Grading "
            "order covers every scenario before repeating any: 61 gradable runs span 13 "
            "scenarios, and repeats of one scenario are not independent judgements."
        ),
    )
    p.add_argument("--next", action="store_true", help="show the next ungraded run, blind")
    p.add_argument("--grade", metavar="RUN_ID", default=None, help="record a grade for this run")
    p.add_argument("--regrade", metavar="RUN_ID", default=None, help="revise after the reveal")
    p.add_argument("--level", choices=("same_mechanism", "adjacent", "different"), default=None)
    p.add_argument("--reason", default=None, help="one sentence; required with --grade")
    p.add_argument("--grader", default="", help="who graded, recorded on the row")
    p.add_argument("--report", action="store_true", help="print the agreement panel")
    p.add_argument("--runs-root", default=None)
    p.add_argument("--ledger", default=None)
    return p


def judged_runs(root: Path) -> dict[str, dict[str, Any]]:
    """Every run the judge has scored, keyed by run id.

    A run without a `judge` block has not been judged, so there is nothing to calibrate against -
    it is skipped rather than counted as a disagreement.

    **The key comes from `judge.AGREEMENT_KEY`, not from a literal here.** This function read
    `judge["agreement"]` for a day. No manifest has ever held that key - `JudgeResult.agreement`
    serialises as `root_cause_agreement` - so it skipped **all 78 judged runs** and printed
    "every judged run has a grade (0 recorded)", which reads exactly like a finished job. A
    filter that silently matches nothing is the defect T4.1b's clause is about, arriving in the
    one harness whose whole purpose is checking whether an automated verdict can be trusted.
    """
    from evalharness.judge import AGREEMENT_KEY

    found: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return found
    for directory in sorted(root.iterdir()):
        manifest_path = directory / "manifest.json"
        if not (directory.is_dir() and manifest_path.is_file()):
            continue
        manifest = json.loads(manifest_path.read_text())
        judge = manifest.get("judge") or {}
        if not judge.get(AGREEMENT_KEY):
            continue
        if abstained(manifest):
            continue
        narratives = sorted(directory.glob("*-narrative.md"))
        found[directory.name] = {
            "run_id": directory.name,
            "scenario_id": manifest.get("scenario_id", ""),
            "agreement": judge[AGREEMENT_KEY],
            "agreement_reason": judge.get("agreement_reason", ""),
            "narrative": narratives[0].read_text() if narratives else "",
        }
    return found


def abstained(manifest: dict[str, Any]) -> bool:
    """Whether the pipeline declined to name a fault class on this run.

    **An abstention has nothing to calibrate against.** ADR-0022 §1.2 makes `unknown` a legal
    answer rather than a wrong one, and the judge - having no claim to compare - grades every
    abstention `different` by construction. Agreeing with that is a free point and disagreeing is
    a free miss; the row measures the grader's guess about a convention, not their reading.

    Measured on the committed record: **17 of 78** judged runs are abstentions, and they account
    for **17 of the 18 `different` verdicts in the entire record**. Including them would have put
    seventeen mechanical rows into a figure whose whole purpose is checking a judgement.
    """
    fault_class = (manifest.get("score") or {}).get("fault_class") or {}
    return bool(fault_class.get("abstained"))


def abstention_count(root: Path) -> int:
    """How many runs the pool excluded. **Counted, never silently dropped** - a pool that shrank
    by 22% without saying so is the same defect one level up."""
    total = 0
    if not root.is_dir():
        return 0
    from evalharness.judge import AGREEMENT_KEY

    for directory in sorted(root.iterdir()):
        manifest_path = directory / "manifest.json"
        if not (directory.is_dir() and manifest_path.is_file()):
            continue
        manifest = json.loads(manifest_path.read_text())
        if (manifest.get("judge") or {}).get(AGREEMENT_KEY) and abstained(manifest):
            total += 1
    return total


def run(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)

    from evalharness import calibration as cal
    from evalharness.judge import recorded_narrative
    from evalharness.run import RUN_ROOT

    root = Path(args.runs_root) if args.runs_root else RUN_ROOT
    ledger = Path(args.ledger) if args.ledger else cal.LEDGER
    judged = judged_runs(root)
    grades = cal.load(ledger)

    # `(scenario_id, judge_level)` per run - what `cal.stratified` needs to cover the record
    # rather than sample it. **The grader is never shown either.**
    strata = {k: (v["scenario_id"], v["agreement"]) for k, v in judged.items()}

    if args.report:
        panel = cal.agreement({k: v["agreement"] for k, v in judged.items()}, grades)
        graded = set(cal.current(grades))
        panel = replace(
            panel,
            abstentions=abstention_count(root),
            scenarios=len({s for run_id, (s, _) in strata.items() if run_id in graded}),
        )
        print("\n".join(panel.render()))
        return 0

    if args.next:
        run_id = cal.next_ungraded(sorted(judged), grades, runs=strata)
        if run_id is None:
            print(f"every judged run has a grade ({len(cal.current(grades))} recorded)")
            return 0
        entry = judged[run_id]
        print(f"run: {run_id}")
        print(f"scenario: {entry['scenario_id']}")
        print("\n--- RECORDED NARRATIVE (what actually happened) ---\n")
        print(recorded_narrative(entry["scenario_id"]))
        print("\n--- AGENT NARRATIVE (what the system under test wrote) ---\n")
        print(entry["narrative"] or "(the run wrote no narrative)")
        # The judge's verdict is deliberately absent. See the module docstring.
        print("\n--- YOUR CALL ---")
        print("Does the agent narrative name the same mechanism? same_mechanism | adjacent |")
        print("different.  `adjacent` is right subsystem, wrong mechanism.")
        print(f"\n  faultline-calibrate --grade {run_id} --level <level> --reason '<one sentence>'")
        return 0

    if args.grade or args.regrade:
        run_id = args.grade or args.regrade
        if run_id not in judged:
            print(f"REFUSED: {run_id} has no judged verdict to calibrate against")
            return 3
        if not args.level or not args.reason:
            print("REFUSED: --level and --reason are both required")
            return 3
        standing = cal.current(grades).get(run_id)
        if args.grade and standing is not None:
            print(
                f"REFUSED: {run_id} already has a standing grade ({standing.agreement}).\n"
                "  To revise after seeing the judge's answer, use --regrade - it writes a second\n"
                "  record marked not-blind, which the agreement figure excludes."
            )
            return 3
        from datetime import UTC, datetime

        if args.regrade:
            if standing is None:
                print(f"REFUSED: {run_id} has no grade to revise")
                return 3
            written = cal.record(cal.regrade(standing, args.level, args.reason), ledger)
        else:
            written = cal.record(
                cal.Grade(
                    run_id=run_id,
                    scenario_id=judged[run_id]["scenario_id"],
                    agreement=args.level,
                    reason=args.reason,
                    graded_at=datetime.now(UTC).isoformat(),
                    grader=args.grader,
                ),
                ledger,
            )
        print(f"recorded: {written.agreement} ({'blind' if written.blind else 'not blind'})")
        # **The reveal, and only now.**
        entry = judged[run_id]
        print(f"\nthe judge said: {entry['agreement']}")
        if entry["agreement_reason"]:
            print(f"  {entry['agreement_reason']}")
        print(
            "\nagreed."
            if entry["agreement"] == written.agreement
            else "\ndisagreed. Both records stand; neither is corrected to match the other."
        )
        return 0

    parser().print_help()
    return 0


def run_cli() -> None:  # pragma: no cover - console entry point
    raise SystemExit(run())
