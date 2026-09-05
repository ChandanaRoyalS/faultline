"""`faultline-blind-rca` — draw a fault you are not told the name of, and time yourself (T4.7).

    faultline-blind-rca --draw
    faultline-blind-rca --answer --fault-class resource_exhaustion --service adservice
    faultline-blind-rca --give-up --notes "..."
    faultline-blind-rca --status

**The module this drives had no caller for one commit**, which is the defect this project has now
found seven times: `blind.py` shipped with the draw, the seal, the pool arithmetic and tests for
all three, and nothing that ran them. A protocol describing a procedure nobody can execute is a
protocol nobody has executed.

## The order, and why each step is where it is

**Gate, then draw, then inject, then settle, then start the clock.** The baseline gate first
because a world with an open incident is one where the draw is not the only thing wrong with it.
The settle before the clock because the pipeline's own latency figure starts after it - a
responder timed from the first episode would be timed partly on waiting for the blast radius to
fill, and the comparison T4.7 exists to make would be unfair in the direction that flatters the
pipeline.

**The clock stops when the answer is recorded, and the reveal comes after.** `--answer` writes
the attempt, *then* opens the seal, *then* reverts. An operator who saw the scenario name before
her answer was on disk would be recording a different thing.

## What it refuses

A second draw while one is sealed; an answer with no draw; an answer that names no fault class
unless it is `--give-up`. Each of those is a state where the number produced would not mean what
the label on it says.
"""

from __future__ import annotations

import argparse
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

POOL: tuple[str, ...] = (
    "ad-memory-squeeze",
    "cart-bad-image-tag",
    "cart-dependency-latency",
    "cart-redis-misconfig",
    "frauddetection-memory-squeeze",
)
"""Dev sweep 9's five, so every manual timing has a pipeline timing beside it on the same scenario
at world generation `f5bd108f4f70`.

**Pinned here rather than passed**, and named in `PROTOCOL-2026-09-05.md` before the first draw.
A pool chosen per-invocation is a pool that can be narrowed after a bad attempt, which is the
self-timed version of re-running a scored run to improve a number.
"""


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="faultline-blind-rca",
        description=(
            "Draw one of five faults without being told which, investigate it, and record how "
            "long it took (T4.7). The responder authored these scenarios; blinding the draw makes "
            "the timing measure recognition rather than confirmation, and does not make it clean."
        ),
        epilog="Exit codes: 0 done; 3 refused - see the message, nothing was injected or recorded.",
    )
    p.add_argument(
        "--draw", action="store_true", help="gate, pick, inject, settle, start the clock"
    )
    p.add_argument("--answer", action="store_true", help="record a conclusion and stop the clock")
    p.add_argument("--give-up", action="store_true", help="record an abandoned investigation")
    p.add_argument("--status", action="store_true", help="is a draw open, and for how long")
    p.add_argument("--fault-class", default="")
    p.add_argument("--service", default="")
    p.add_argument("--notes", default="")
    p.add_argument("--postgres-dsn", default=None)
    p.add_argument("--seal", default=None)
    p.add_argument("--ledger", default=None)
    return p


def _sh(argv: list[str]) -> tuple[int, str]:
    done = subprocess.run(argv, capture_output=True, text=True, check=False)
    return done.returncode, (done.stdout + done.stderr).strip()


def run(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)

    from evalharness import blind
    from evalharness import manual_rca as rca

    seal_path = Path(args.seal) if args.seal else blind.SEAL
    ledger = Path(args.ledger) if args.ledger else rca.LEDGER

    if args.status:
        if not blind.sealed(seal_path):
            attempted = [a.scenario_id for a in rca.load(ledger)]
            left = blind.remaining(list(POOL), attempted)
            print(f"no draw open. {len(attempted)} attempted, {len(left)} left in the pool.")
            return 0
        held = blind.unseal(seal_path)
        started = datetime.fromisoformat(held.clock_started_at)
        running = (datetime.now(UTC) - started).total_seconds() / 60
        # **The scenario is not printed.** `--status` exists so the operator can check her clock
        # without opening the seal, and a status line that named the draw would be the seal.
        print(f"a draw is open on incident {held.incident_id}, running {running:.1f} min.")
        print(f"  drawn from {held.prior}. Answer with --answer or --give-up.")
        return 0

    if args.draw:
        return _draw(args, blind, rca, seal_path, ledger)
    if args.answer or args.give_up:
        return _record(args, blind, rca, seal_path, ledger)

    parser().print_help()
    return 0


def _draw(args, blind, rca, seal_path: Path, ledger: Path) -> int:
    from evalharness import gate
    from evalharness.run import open_incidents, settling_incidents, wait_for_incident

    if blind.sealed(seal_path):
        print("REFUSED: a draw is already open. Answer or give up on it first.")
        return 3

    attempted = [a.scenario_id for a in rca.load(ledger)]
    try:
        picked = blind.draw(list(POOL), attempted)
    except blind.DrawError as refusal:
        print(f"REFUSED: {refusal}")
        return 3

    dsn = args.postgres_dsn
    if dsn is None:
        from faultline.context.settings import ContextSettings

        dsn = ContextSettings().postgres_dsn

    # **The gate first.** A world with an open incident is one where the draw is not the only
    # thing wrong with it, and injecting into it would time an investigation of two faults.
    print("baseline gate...")
    try:
        reading = gate.require(open_incidents(dsn), settling_incidents(dsn), runs_remaining=1)
    except gate.GateRefusedError as refused:
        print(f"REFUSED: {refused}\nNothing was injected and no draw was sealed.")
        return 3
    print(f"  {reading.summary if hasattr(reading, 'summary') else 'clean'}")

    injected_at = datetime.now(UTC)
    code, out = _sh(["faultline-inject", "start", picked])
    if code != 0:
        print(f"REFUSED: the injection failed.\n{out}\nNo draw was sealed.")
        return 3

    print("waiting for the orchestrator to correlate...")
    try:
        incident_id = wait_for_incident(dsn, injected_at)
    except Exception as never_alerted:
        _sh(["faultline-inject", "stop", picked])
        print(f"REFUSED: no incident opened ({never_alerted}). The fault was reverted.")
        return 3

    # **Settle before the clock, not after.** The pipeline's latency starts here too.
    print(f"  settling {blind.SETTLE_AFTER_ALERT_SECONDS}s so the blast radius fills")
    time.sleep(blind.SETTLE_AFTER_ALERT_SECONDS)

    blind.seal(
        blind.Draw(
            scenario_id=picked,
            pool=POOL,
            drawn_at=injected_at.isoformat(),
            incident_id=incident_id,
            clock_started_at=blind.now(),
        ),
        seal_path,
    )
    remaining = len(blind.remaining(list(POOL), attempted))
    print("")
    print(f"INCIDENT {incident_id}")
    print(f"  drawn blind from {remaining} remaining of {len(POOL)}. The clock is running.")
    print("  Evidence: Prometheus, Loki, Jaeger, the change log, the UI. Not the bundle, not")
    print("  incident.md, not any run directory, not the seal.")
    print("  faultline-blind-rca --answer --fault-class ... --service ...")
    return 0


def _record(args, blind, rca, seal_path: Path, ledger: Path) -> int:
    if not blind.sealed(seal_path):
        print("REFUSED: no draw is open. Nothing is being timed.")
        return 3
    held = blind.unseal(seal_path)

    if not args.give_up and not (args.fault_class and args.service):
        # The clock keeps running. Refusing and discarding the elapsed time would send the
        # operator back to start a second, shorter investigation of a fault she has now seen.
        print(
            "REFUSED: an answer needs both --fault-class and --service.\n"
            "  T4.2 made which service broke a scored axis, and a reference that answers only\n"
            "  the mechanism cannot be compared on it. If you reached neither, use --give-up.\n"
            "  The clock is still running."
        )
        return 3

    started = datetime.fromisoformat(held.clock_started_at)
    now = datetime.now(UTC)
    note = args.notes
    provenance = f"blind draw, {held.prior}, incident {held.incident_id}"
    try:
        attempt = rca.record(
            rca.Attempt(
                scenario_id=held.scenario_id,
                started_at=held.clock_started_at,
                finished_at=now.isoformat(),
                elapsed_seconds=(now - started).total_seconds(),
                fault_class="" if args.give_up else args.fault_class,
                service="" if args.give_up else args.service,
                notes=f"{note} [{provenance}]" if note else f"[{provenance}]",
                gave_up=bool(args.give_up),
            ),
            ledger,
        )
    except rca.AttemptError as refused:
        print(f"REFUSED: {refused}\n  The clock is still running and the draw is still sealed.")
        return 3

    # **The reveal, and only now.** Same shape as `faultline-calibrate`: the record is on disk
    # before the answer it was made without is shown.
    seal_path.unlink()
    print(f"recorded: {attempt.elapsed_seconds / 60:.1f} min")
    print(f"  you said : {attempt.fault_class or '(gave up)'} / {attempt.service or '-'}")
    print(f"  it was   : {held.scenario_id}")

    code, out = _sh(["faultline-inject", "stop", held.scenario_id])
    print(f"reverting... {'done' if code == 0 else out}")
    print("")
    print("Wait 300s before the next --draw: a firing inside the orchestrator's settle window")
    print("reopens this incident rather than opening a new one.")
    return 0


def run_cli() -> None:  # pragma: no cover - console entry point
    raise SystemExit(run())
