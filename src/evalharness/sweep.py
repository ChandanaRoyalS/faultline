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
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evalharness import variance

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_ROOT = REPO_ROOT / "evals/scenarios"

MEDIAN_RUN_USD = 0.53
"""Measured over the 87 recorded agent runs that carry a cost: median $0.53, range $0.26-$0.88.

**Printed before the sweep starts, not estimated afterwards.** CLAUDE.md rule 8: a blocker with a
price can be cleared; one without is indistinguishable from a blocker with no solution. An
operator about to spend an hour of world time and real money should see the number first.
"""

DISCARD_RATE = 0.18
"""**22 discarded against 121 runs that started** - 99 scored plus those 22. A sweep is budgeted
against the runs it will start, and a run that never started costs nothing to budget for.

**This read 0.33 for a day, and the 33% was half gate refusals.** 44 of 132 runs carried a
`DISCARDED.md`, but 22 of those had no `injected_at` - they never started, so they cost nothing and
belong in no discard rate. The number this repository quoted, budgeted against, and recorded in
`docs/PLAN.md` as a headline property was exactly double the truth.

**Then it read 0.17, and the denominator was wrong in the other direction.** 22 of *132* put
refusals into the denominator of a rate about runs that happen, so every bad afternoon of refusals
would have made the pipeline look healthier. The denominator is now the runs that started, and
`tests/test_evaldb.py` asserts this constant against the committed record so the two cannot drift.

Both corrections are *readings* of the record. No manifest has been rewritten."""

GATE_REFUSED = 3
PAUSED = 5
CLEARABLE = frozenset({GATE_REFUSED, PAUSED})
"""Exit codes where **nothing was injected and the scenario has not been attempted**.

The harness says so itself: *"THIS IS A PAUSE, NOT A DISCARD - nothing was injected and this
scenario has not been attempted. Recycle, then start again from here."* Retrying one of these is
not a re-run, because there is no run to repeat - which matters, because ADR-0022 section 3.3
forbids re-running a scored run to improve a number and that rule must not be read as forbidding
this.
"""

SETTLE_SECONDS = 300
"""The orchestrator's settle window, and **the reason a sweep could only ever score its first
scenario**.

Measured on the first real B0 sweep: scenario 1 scored, and 2 through 5 were refused with
*"incident … resolved at … and is still inside the orchestrator's 300s settle window - a firing
episode now would reopen it rather than open a new incident, and this run's alerts would be
attributed to the previous one."*

The gate was right and the driver was wrong. Runs back to back cannot work: every scored run
leaves a resolved incident that blocks the next one for five minutes. Mirrors
`OrchestratorSettings.settle_window_seconds`, and `--settle` overrides it for a deployment that
has changed that value.
"""

RETRY_WAIT_SECONDS = 60

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


class UnknownScenarioError(ValueError):
    """A named scope that includes something the catalog cannot run."""


def select(ids: list[str], only: str) -> list[str]:
    """The scenarios a `--only` scope names, in the order it names them.

    **A pure function, and that is deliberate.** The first version of this lived inside `main()`,
    so the only way to test it was to call `main()` - which uses the real shell runner and
    therefore launched actual `faultline-eval` subprocesses. Running the test suite created six
    run directories and, on a machine with a live world, would have injected faults. A parser that
    can only be exercised by running the thing it configures is not a parser anybody can test.

    **Refuses an unknown id rather than narrowing silently.** A pre-registered scope that quietly
    dropped a scenario would produce a sweep whose document claims five and whose record holds
    four, and the discrepancy would surface as an unexplained `n` weeks later.
    """
    wanted = [name.strip() for name in only.split(",") if name.strip()]
    unknown = [name for name in wanted if name not in ids]
    if unknown:
        raise UnknownScenarioError(
            f"not runnable scenarios: {', '.join(unknown)}. Runnable: {', '.join(ids)}"
        )
    return wanted


@dataclass(slots=True)
class Outcome:
    scenario_id: str
    exit_code: int
    attempts: int = 1
    """How many times this scenario was launched. **Above 1 only for clearable refusals**, where
    nothing was injected - never for a discard, which is recorded once and never repeated."""

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
    repeats: int = 1,
    extra: list[str] | None = None,
    runner: Any = None,
    settle: int = 0,
    retries: int = 1,
    sleeper: Any = None,
) -> SweepResult:
    """The catalog, `repeats` times, counting down `--runs-remaining` across the whole job.

    **`repeats` exists because the tier flag alone was a lie.** `faultline-eval --tier weekly`
    writes `repeat_count = 3` into the manifest and runs **once**; nothing in it repeats. A driver
    that passed the tier through and made a single pass would have produced a catalog of runs each
    *declaring* R = 3 while R = 1 actually happened - a corrupt fingerprint, and precisely the
    "declared R and observed runs per scenario differ" mismatch `compare.report` warns about.

    **`settle` exists because runs cannot go back to back.** Every scored run leaves a resolved
    incident, and a firing inside the orchestrator's 300s settle window **reopens that incident
    rather than opening a new one** - so the next scenario's alerts would be attributed to the
    previous scenario. The first real sweep scored 1 of 5 and the gate refused the other four for
    exactly this. Waiting after a run that injected is cheaper than retrying it afterwards.

    **A clearable refusal is retried; a discard never is.** Exit 3 and 5 mean *nothing was
    injected and this scenario has not been attempted* - the harness says so in the refusal - so
    launching again is not a re-run and ADR-0022 section 3.3's ban on re-running a scored run to
    improve a number does not reach it. A discard (exit 4) is recorded once and left alone.

    **Catalog-major, not scenario-major**: every scenario once before any scenario twice. Running a
    scenario's three repeats back to back would measure it against three nearly identical world
    states and understate run-to-run variance, which is the one quantity R > 1 exists to estimate.

    **`settle` and `retries` default to off, and that is deliberate.** The first version defaulted
    them to the real 300s and 6, and the test suite hung: every existing test called `sweep()`
    without a sleeper and tried to nap for twenty minutes. Waiting is a property of *running a
    sweep against a live world*, which is `main()`'s job; a library function whose default
    behaviour is to sleep is one nobody can call in a test without knowing to disarm it.

    `runner` and `sleeper` are the seams the tests substitute at. The default `runner` shells out to
    `faultline-eval`, which is what ADR-0004 requires: the harness drives the product through its
    public interface, and its **exit code is the contract**.
    """
    launch = runner or _shell
    wait = sleeper or time.sleep
    result = SweepResult()
    total = len(ids) * repeats
    done = 0
    injected_something = False
    # **Set when a scenario exhausts every retry on a clearable code; the scenarios after it are
    # launched once each instead of `retries` times.**
    #
    # A retry answers "has the world settled yet". It cannot answer "is there a credential", and
    # on 2026-09-04 a sweep asked six times per scenario, sixty seconds apart, whether an
    # unresolvable API key had resolved itself: thirty launches and twenty-five minutes for a
    # condition the first six had already proven unchangeable. The signal is not the exit code,
    # which is 3 either way - it is the *previous scenario having burned its whole budget*. A
    # refusal that survived every attempt on the scenario before it is not transient.
    #
    # Every scenario is still launched, so every scenario still gets an outcome row: the sweep
    # reports the catalog it attempted, which is what T4.4 is about. Only the re-asking stops, and
    # one scored run clears it - a world that let a run through is one whose refusals are worth
    # retrying again.
    standing_refusal = False

    for pass_number in range(1, repeats + 1):
        for scenario_id in ids:
            done += 1
            argv = [
                "faultline-eval",
                scenario_id,
                "--runs-remaining",
                str(total - done + 1),
                *(extra or []),
            ]
            # **Wait before, not after.** The block is the *previous* incident's settle window, so
            # the pause belongs in front of the run that would trip over it - and only when
            # something has actually been injected, so a sweep whose first scenarios all refuse
            # does not sit idle for five minutes apiece having broken nothing.
            if injected_something and settle:
                print(f"--- settling {settle}s before {scenario_id}", flush=True)
                wait(settle)

            code = 0
            budget = 1 if standing_refusal else retries
            if standing_refusal:
                print(
                    f"--- not retrying {scenario_id}: the previous scenario refused on every one "
                    f"of {retries} attempts, so the condition is standing rather than transient",
                    flush=True,
                )
            for attempt in range(1, budget + 1):
                label = f"[{done}/{total}] pass {pass_number}/{repeats} {scenario_id}"
                tail = "" if attempt == 1 else f"  (attempt {attempt}/{budget})"
                print(f"\n=== {label}{tail}   $ {' '.join(argv)}", flush=True)
                code = int(launch(argv))
                if code not in CLEARABLE or attempt == budget:
                    break
                print(
                    f"=== {scenario_id}: {EXIT_NAMES.get(code, code)} - nothing was injected, "
                    f"retrying in {RETRY_WAIT_SECONDS}s",
                    flush=True,
                )
                wait(RETRY_WAIT_SECONDS)

            if code == 0:
                injected_something = True
                standing_refusal = False
            elif code in CLEARABLE and budget > 1:
                standing_refusal = True
            result.outcomes.append(
                Outcome(scenario_id=scenario_id, exit_code=code, attempts=attempt)
            )
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
    p.add_argument(
        "--only",
        default=None,
        metavar="ID,ID,...",
        help=(
            "run exactly these scenarios instead of the catalog. **For a pre-registered scope**: "
            "a registration that names five scenarios is a commitment to five, and running the "
            "catalog instead would be a different experiment than the one committed before the "
            "fact. Refuses an id that is not runnable rather than silently skipping it"
        ),
    )
    p.add_argument("--max-tool-calls", default=None)
    p.add_argument("--max-tool-calls-changes", default=None)
    p.add_argument("--max-tokens", default=None)
    p.add_argument("--baseline", choices=("b0", "b1", "b2"), default=None)
    p.add_argument("--postgres-dsn", default=None)
    p.add_argument(
        "--settle",
        type=int,
        default=SETTLE_SECONDS,
        metavar="SECONDS",
        help=(
            "wait this long after a run that injected, before the next one. Mirrors the "
            "orchestrator's settle window: a firing inside it reopens the previous incident "
            "instead of opening a new one, so back-to-back runs attribute one scenario's alerts "
            "to another. 0 disables it (default: %(default)s)"
        ),
    )
    p.add_argument(
        "--retries",
        type=int,
        default=6,
        metavar="N",
        help=(
            "how many times to relaunch a scenario the gate refused. A refusal means nothing was "
            "injected and the scenario has not been attempted, so this is not a re-run. A "
            "discarded run is never retried (default: %(default)s)"
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    ids = runnable()

    if args.only:
        try:
            ids = select(ids, args.only)
        except UnknownScenarioError as refusal:
            print(f"REFUSED: {refusal}")
            return 3

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

    # **The declared repeat count and the number of passes are the same number.** A tier that
    # declared R = 3 while one pass ran would put a corrupt fingerprint on every run in the sweep.
    repeats = variance.TIERS[args.tier][0] if args.tier else 1
    estimate = len(ids) * repeats
    print(
        f"{len(ids)} scenario(s) x {repeats} pass(es) = {estimate} run(s). "
        f"At the recorded median of ${MEDIAN_RUN_USD:.2f}/run that is about "
        f"${estimate * MEDIAN_RUN_USD:.0f}, and the measured discard rate is "
        f"{DISCARD_RATE:.0%} - budget about ${estimate * MEDIAN_RUN_USD / (1 - DISCARD_RATE):.0f}."
    )
    result = sweep(ids, repeats=repeats, extra=extra, settle=args.settle, retries=args.retries)
    print("\n".join(result.render()))
    return result.exit_code


def run_cli() -> None:  # pragma: no cover - console entry point
    raise SystemExit(main())
