"""`faultline-manual-rca` — time yourself investigating, one scenario at a time (T4.7).

    faultline-manual-rca --start ad-memory-squeeze
    faultline-manual-rca --finish ad-memory-squeeze \
        --fault-class resource_exhaustion --service adservice --notes "..."
    faultline-manual-rca --give-up ad-memory-squeeze --notes "..."
    faultline-manual-rca --report

**The clock is wall-clock between `--start` and `--finish`**, not a number typed in afterwards. A
self-reported duration is a memory of a duration, and the difference between the two is exactly
the direction that flatters the person reporting it.

`--give-up` is a first-class outcome, not a failure to use the tool. An investigation abandoned
after twenty minutes is data about difficulty, and dropping it would make the median a median over
the easy ones.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="faultline-manual-rca",
        description=(
            "Self-timed manual investigation, to give the MTTR claim a left-hand side (T4.7). "
            "Reported as 'n=5, self-timed, indicative' - and with the contamination stated: the "
            "responder authored these scenarios, so this is a floor on human time rather than an "
            "estimate of it."
        ),
    )
    p.add_argument("--start", metavar="SCENARIO", default=None)
    p.add_argument("--finish", metavar="SCENARIO", default=None)
    p.add_argument("--give-up", metavar="SCENARIO", default=None)
    p.add_argument("--fault-class", default="")
    p.add_argument("--service", default="")
    p.add_argument("--notes", default="")
    p.add_argument("--report", action="store_true")
    p.add_argument("--ledger", default=None)
    p.add_argument("--clock", default=None, help=argparse.SUPPRESS)
    return p


def _clockfile(ledger: Path) -> Path:
    return ledger.parent / "in-progress.json"


def run(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)

    from evalharness import manual_rca as rca

    ledger = Path(args.ledger) if args.ledger else rca.LEDGER
    clock = Path(args.clock) if args.clock else _clockfile(ledger)

    if args.report:
        print("\n".join(rca.Reference(attempts=tuple(rca.load(ledger))).render()))
        return 0

    if args.start:
        clock.parent.mkdir(parents=True, exist_ok=True)
        if clock.exists():
            running = json.loads(clock.read_text())
            print(
                f"REFUSED: {running['scenario_id']} is already being timed since "
                f"{running['started_at']}.\n"
                "  Finish or give up on it first. Two clocks at once means neither is a duration."
            )
            return 3
        clock.write_text(
            json.dumps({"scenario_id": args.start, "started_at": datetime.now(UTC).isoformat()})
        )
        print(f"timing {args.start}. Investigate, then --finish or --give-up.")
        return 0

    target = args.finish or args.give_up
    if not target:
        parser().print_help()
        return 0

    if not clock.exists():
        print(f"REFUSED: nothing is being timed. Start with --start {target}.")
        return 3
    running = json.loads(clock.read_text())
    if running["scenario_id"] != target:
        print(f"REFUSED: {running['scenario_id']} is being timed, not {target}.")
        return 3

    started = datetime.fromisoformat(running["started_at"])
    now = datetime.now(UTC)
    try:
        attempt = rca.record(
            rca.Attempt(
                scenario_id=target,
                started_at=running["started_at"],
                finished_at=now.isoformat(),
                elapsed_seconds=(now - started).total_seconds(),
                fault_class="" if args.give_up else args.fault_class,
                service="" if args.give_up else args.service,
                notes=args.notes,
                gave_up=bool(args.give_up),
            ),
            ledger,
        )
    except rca.AttemptError as refused:
        # The clock is left running on purpose: refusing the record and discarding the elapsed
        # time would make the operator start again and time a second, shorter investigation.
        print(f"REFUSED: {refused}")
        return 3
    clock.unlink()
    minutes = attempt.elapsed_seconds / 60
    print(
        f"recorded {target}: {minutes:.1f} min, "
        + ("abandoned" if attempt.gave_up else f"{attempt.fault_class} / {attempt.service}")
    )
    return 0


def run_cli() -> None:  # pragma: no cover - console entry point
    raise SystemExit(run())
