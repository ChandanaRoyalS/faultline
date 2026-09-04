"""`faultline-sweep` — the whole catalog, unattended (Gate 4's first condition).

Gate 4 reads: *"`make eval` injects, runs, scores, and reports all 10 scenarios **unattended**"*.
`faultline-eval` takes exactly one `scenario_id`, and until now the only thing that ran a catalog
was **a shell loop inside `.github/workflows/eval-nightly.yml`** — so the capability existed, in
CI, in bash, untested, and reachable by nobody at a terminal. `docs/GATES.md` has listed this as
a G4 blocker since before the Phase 4 audit.

Three things this has to get right, and each was already solved once inside that shell loop:

**The countdown.** `faultline-eval --runs-remaining N` exists because the baseline gate projects
the world's memory forward over the work still to come and refuses a sweep at its *start* rather
than partway through (T7.32). A driver that passed `--single-run` per scenario would defeat that,
and one that passed a constant would let the projection drift.

**A discard must not end the sweep.** Every outcome is a row (T4.4), and a catalog run that
stopped at the first failure would report *the catalog it got through* while looking like a
catalog run. 32% of every run ever started has been discarded, so this is the common case and
not the edge one.

**A scenario whose bundle carries `INVALID.md` is not runnable.** `currency-cpu-throttle` and
`flag-service-crashloop` produced nothing observable; including them would put two guaranteed
failures in every sweep and quietly lower every rate this harness prints.

## What it does not do

**It does not judge, and it does not aggregate.** `faultline-judge` is a separate pass over the
run tree and `faultline-eval-db load` is another, both by design: judging inside the sweep would
put judge spend and judge latency into the figures the sweep is measuring. The summary printed
here is a count of outcomes, not a score.
"""

from __future__ import annotations

import argparse
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_ROOT = REPO_ROOT / "evals/scenarios"

EXIT_NAMES = {
    0: "scored",
    2: "world lock",
    3: "gate refused",
    4: "discarded",
    5: "paused",
    6: "invalid",
}
"""Short labels for the summary. **The authority is `run.EXIT_CODES`**, and a test asserts this
covers it — a second hand-written copy of a contract is how a driver comes to print `exit 6` for
a run the harness calls INVALID."""


def runnable(root: Path = SCENARIO_ROOT) -> list[str]:
    """Every scenario that can be run, in a stable order.

    A bundle carrying `INVALID.md` is excluded: its fault produced nothing observable, so a run
    of it can only fail, and **counting guaranteed failures in a catalog rate would move every
    number this harness prints** without anything about the pipeline changing.
    """
    from evalharness.scenario import load_catalog

    def blocked(scenario_id: str) -> bool:
        return any(
            (root / "artifacts" / split / scenario_id / "INVALID.md").is_file()
            for split in ("dev", "holdout")
        )

    return sorted(s.id for s in load_catalog(root) if not blocked(s.id))


@dataclass(slots=True)
class Outcome:
    scenario_id: str
    exit_code: int

    @property
    def name(self) -> str:
        return EXIT_NAMES.get(self.exit_code, f"exit {self.exit_code}")

    @property
    def scored(self) -> bool:
        return self.exit_code == 0


@dataclass(slots=True)
class SweepResult:
    """What a pass over the catalog did. **Never a score** — see the module docstring."""

    outcomes: list[Outcome] = field(default_factory=list)

    @property
    def scored(self) -> int:
        return sum(1 for o in self.outcomes if o.scored)

    @property
    def exit_code(self) -> int:
        """`0` when every scenario scored, `1` otherwise.

        **Not "nothing crashed".** A sweep where half the catalog was discarded ran perfectly and
        produced half a measurement, and a driver that exited 0 on it would let CI and a reader
        take a partial catalog for a whole one.
        """
        return 0 if self.outcomes and self.scored == len(self.outcomes) else 1

    def render(self) -> list[str]:
        counts = Counter(o.name for o in self.outcomes)
        lines = [
            "",
            f"SWEEP: {self.scored}/{len(self.outcomes)} scored",
            "  " + " · ".join(f"{name} {n}" for name, n in sorted(counts.items())),
        ]
        not_scored = [o for o in self.outcomes if not o.scored]
        if not_scored:
            lines += ["", "  not scored:"]
            lines += [f"    {o.scenario_id:34} {o.name}" for o in not_scored]
        lines += [
            "",
            "This is a count of outcomes, not a score. `faultline-judge` grades the narratives "
            "and `faultline-eval-db load` aggregates; neither runs here, because judging inside "
            "the sweep would put judge spend into the figures the sweep is measuring.",
        ]
        return lines


def sweep(
    ids: list[str],
    *,
    extra: list[str] | None = None,
    runner: Any = None,
) -> SweepResult:
    """Run each scenario once, counting down `--runs-remaining`.

    `runner` is the seam the tests substitute at: a callable taking the argv list and returning an
    exit code. The default shells out to `faultline-eval`, which is what ADR-0004 requires — the
    harness drives the product through its public interface, and its **exit code is the contract**.
    """
    launch = runner or _shell
    result = SweepResult()
    for index, scenario_id in enumerate(ids):
        remaining = len(ids) - index
        argv = ["faultline-eval", scenario_id, "--runs-remaining", str(remaining), *(extra or [])]
        print(f"\n=== [{index + 1}/{len(ids)}] {scenario_id}   $ {' '.join(argv)}", flush=True)
        code = int(launch(argv))
        result.outcomes.append(Outcome(scenario_id=scenario_id, exit_code=code))
        print(f"=== {scenario_id}: {EXIT_NAMES.get(code, code)}", flush=True)
    return result


def _shell(argv: list[str]) -> int:  # pragma: no cover - the subprocess path
    return subprocess.run(argv, check=False).returncode


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="faultline-sweep",
        description=(
            "Run every runnable scenario once, unattended (Gate 4). Drives `faultline-eval` as a "
            "subprocess and counts down --runs-remaining so the baseline gate can project the "
            "world's memory over the whole sweep."
        ),
        epilog=(
            "Exit codes: 0 every scenario scored; 1 at least one did not. A partial catalog is "
            "not a pass - it is half a measurement wearing a whole one's name."
        ),
    )
    p.add_argument("--tier", default=None, help="passed through to faultline-eval (T4.6)")
    p.add_argument("--list", action="store_true", help="print the scenarios and exit")
    p.add_argument("--max-tool-calls", default=None)
    p.add_argument("--max-tool-calls-changes", default=None)
    p.add_argument("--max-tokens", default=None)
    p.add_argument("--baseline", choices=("b0", "b1", "b2"), default=None)
    p.add_argument("--postgres-dsn", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    ids = runnable()

    if args.list:
        print(f"{len(ids)} runnable scenario(s):")
        for scenario_id in ids:
            print(f"  {scenario_id}")
        return 0
    if not ids:
        print("no runnable scenarios; nothing to sweep")
        return 1

    extra: list[str] = []
    for flag in (
        "tier",
        "max_tool_calls",
        "max_tool_calls_changes",
        "max_tokens",
        "baseline",
        "postgres_dsn",
    ):
        value = getattr(args, flag)
        if value is not None:
            extra += [f"--{flag.replace('_', '-')}", str(value)]

    result = sweep(ids, extra=extra)
    print("\n".join(result.render()))
    return result.exit_code


def run_cli() -> None:  # pragma: no cover - console entry point
    raise SystemExit(main())
