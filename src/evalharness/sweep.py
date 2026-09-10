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

**Unmoved on 2026-09-09, and the reason is worth saying.** Dev sweep 12's first attempt ran 15
scored runs at $0.56-$0.85 - inside the range, and with a median nearer $0.69 than $0.53, so the
estimate this constant prints under-predicted that sweep by about a third. It is left alone because
a run's cost is in the trajectory store rather than in its manifest, so unlike `DISCARD_RATE` this
number cannot be recomputed from the committed tree and no guard asserts it. **Treat the printed
estimate as a floor at this stamp**; the four-specialist pipeline costs more than the three-
specialist one did, which is the whole reason prediction 11 registers a cost range.

**Printed before the sweep starts, not estimated afterwards.** CLAUDE.md rule 8: a blocker with a
price can be cleared; one without is indistinguishable from a blocker with no solution. An
operator about to spend an hour of world time and real money should see the number first.
"""

DISCARD_RATE = 0.11
"""**24 discarded against the runs that started** - the scored ones plus those 24. A sweep is
budgeted against the runs it will start, and a run that never started costs nothing to budget for.

**0.15 → 0.13 on 2026-09-09**, when dev sweep 12's first attempt added 15 scored runs and no
discards to the record. **0.13 → 0.11 on 2026-09-10**, when arm A's thirty and arm B's six did the
same. `test_the_correction_holds_on_the_committed_record` moved it both times: the constant is
derived from the tree and is asserted against it, so it tracks rather than ages. **Expect it to
keep falling while sweeps land clean runs**, and note what that means - this is a rate over the
whole history, so a recorder that has got better shows up here as a smaller number rather than as
a claim anyone had to make.

**This read 0.33 for a day, and the 33% was half gate refusals.** 44 of 132 runs carried a
`DISCARDED.md`, but 22 of those had no `injected_at` - they never started, so they cost nothing and
belong in no discard rate. The number this repository quoted, budgeted against, and recorded in
`docs/PLAN.md` as a headline property was exactly double the truth.

**Then it read 0.17, and the denominator was wrong in the other direction.** 22 of *132* put
refusals into the denominator of a rate about runs that happen, so every bad afternoon of refusals
would have made the pipeline look healthier. The denominator is now the runs that started, and
`tests/test_evaldb.py` asserts this constant against the committed record so the two cannot drift.

**Then it read 0.18, and the record moved under it.** This third movement is not a correction: the
arithmetic was right both times. R=3 on the five (`evals/runs/SWEEP-2026-09-06-r3.md`) added fifteen
runs that all scored - no discard, no `INVALID`, no errored tool call - and fifteen clean runs in a
denominator of 133 pull the rate from 0.165 to 0.149. The constant had drifted out of the test's
+/-0.02 band by the time `make check` next ran, which is the test doing the job it was written for.

The first two changes are *readings* of the record; this one is the record itself. **No manifest has
been rewritten in any of the three.** Expect this number to keep moving, and to keep being caught
here rather than in a budget line an operator has already acted on."""

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


def runnable(root: Path = SCENARIO_ROOT, *, holdout: bool = False) -> list[str]:
    """Every scenario that can be run, in a stable order. **Dev only unless `holdout` is set.**

    A bundle carrying `INVALID.md` is excluded: its fault produced nothing observable, so a run
    of it can only fail, and **counting guaranteed failures in a catalog rate would move every
    number this harness prints** without anything about the pipeline changing.

    **Two more exclusions, found by reading `--list` (finding thirty-four, T5.6).** A scenario whose
    YAML says `blocked: true` has no bundle at all - `bundle_for` cannot load it - and the first
    version of this function did not look at the field, so `make eval`'s catalog carried four
    scenarios that would crash the sweep at their turn. And `load_catalog` recurses, so the
    schema's worked example under `examples/` was in the catalog too. Neither is a scenario a
    sweep can attempt; both were on the list Gate 4's command would run unattended.

    **A fourth exclusion, and it cost a whole sweep (dev sweep 12, 2026-09-08).** Holdout scenarios
    were in this list from the start. `faultline-eval` refuses them without `--holdout` - correctly,
    because ADR-0008's axis 1 makes a holdout entry a different experiment that should be hard to
    start by accident - so a catalog sweep attempted three of them once per pass and was refused
    nine times. **The refusals were harmless; their place in the count was not.** The baseline gate
    projects kafka's growth over `--runs-remaining`, so three scenarios that could never run still
    inflated the projection that decides whether the sweep may start at all.

    `holdout=True` puts them back, for a driver that means it. `PREREGISTRATION-T6.1.md` section 4
    said *"the ten dev scenarios"* and named a command that attempted thirteen; this is the
    difference between those two sentences.
    """
    from evalharness.scenario import Scenario

    def invalid(scenario_id: str) -> bool:
        return any(
            (root / "artifacts" / split / scenario_id / "INVALID.md").is_file()
            for split in ("dev", "holdout")
        )

    catalog = (Scenario.from_yaml(path) for path in sorted(root.glob("*.yaml")))
    return sorted(
        s.id
        for s in catalog
        if not s.blocked and not invalid(s.id) and (holdout or s.split != "holdout")
    )


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
    declared_repeats: int = 1
    """The R every run in this sweep wrote into its manifest. Compared against what the world
    actually gave each scenario - see `divergence`."""

    aborted: str | None = None
    """Why the sweep stopped early, or `None` if it ran the catalog out.

    **Set only when the world stopped it, never when a scenario did.** The rest of this class
    reports outcomes for everything that was launched; this reports what was not, and says so
    rather than letting a short `outcomes` list read as a short catalog.
    """

    start_pass: int = 1
    """The pass this invocation began at. `1` for a whole sweep; higher when resuming one that
    an outside condition stopped (`--start-pass`). The passes before it are the operator's claim
    to have run elsewhere, and `divergence` expects only the passes this invocation ran."""

    @property
    def passes_run(self) -> int:
        return self.declared_repeats - self.start_pass + 1

    @property
    def scored(self) -> int:
        return sum(1 for o in self.outcomes if o.scored)

    @property
    def divergence(self) -> dict[str, int]:
        """Scenarios that scored fewer times than their manifests declare, and how many they got.

        **The failure this exists to name (dev sweep 12, 2026-09-08).** `--tier weekly` writes
        `repeat_count: 3` into every manifest. The gate then refused the first fifteen slots, so
        five scenarios scored twice and five scored once - **fifteen runs each declaring R = 3 on a
        world that never gave any of them three.** That is a corrupt fingerprint on every run, and
        the exact "declared R and observed runs per scenario differ" mismatch `compare.report`
        warns about; the sweep printed `15/39 scored` and said nothing about it.

        `test_a_tier_that_declares_three_repeats_runs_the_catalog_three_times` covers the driver
        making three passes. It cannot cover the world refusing them, which is what happened.
        """
        scored = Counter(o.scenario_id for o in self.outcomes if o.scored)
        attempted = {o.scenario_id for o in self.outcomes}
        return {
            scenario: scored.get(scenario, 0)
            for scenario in sorted(attempted)
            if scored.get(scenario, 0) != self.passes_run
        }

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
        if self.start_pass > 1:
            lines += [
                "",
                f"  RESUMED: this invocation ran passes {self.start_pass}-{self.declared_repeats} "
                f"of a declared {self.declared_repeats}. Passes 1-{self.start_pass - 1} are the "
                "operator's claim to have scored elsewhere (--start-pass); the figures below are "
                "for this invocation only, and `faultline-eval-db` is where the whole arm is read.",
            ]
        if self.aborted is not None:
            lines += [
                "",
                "  *** SWEEP ABORTED - THIS IS NOT THE CATALOG ***",
                f"  {self.aborted}",
                "  Fix the world, then run the sweep again. The scenarios that did score are "
                "recorded and are not re-runs to redo; what is missing was never attempted.",
            ]
        not_scored = [o for o in self.outcomes if not o.scored]
        if not_scored:
            lines += ["", "  not scored:"]
            lines += [f"    {o.scenario_id:34} {o.name}" for o in not_scored]
        diverged = self.divergence
        if diverged and self.declared_repeats > 1:
            lines += [
                "",
                f"  *** DECLARED R = {self.declared_repeats}, OBSERVED FEWER ***",
                "  Every run in this sweep wrote "
                f"repeat_count = {self.declared_repeats} into its manifest, and these scenarios "
                "did not score that many times:",
            ]
            lines += [f"    {name:34} scored {n}" for name, n in diverged.items()]
            lines += [
                "  Those runs carry a repeat count the world did not give them. They are not the "
                "sweep that was registered, and pooling them as one would be the mismatch "
                "`compare.report` warns about. Re-run, or report the divergence with the figures.",
            ]
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
    recycler: Any = None,
    start_pass: int = 1,
) -> SweepResult:
    """The catalog, `repeats` times, counting `--runs-remaining` down **within each pass**.

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

    **`recycler` exists because the countdown and the gate disagreed, and the gate won (dev sweep
    12, 2026-09-08).** The baseline gate projects kafka's growth forward over `--runs-remaining` and
    refuses if the forecast crosses 90 %. The first version counted down across the *whole* job, so
    a three-pass sweep told the gate about 30-39 runs at once: the forecast was 124 %, and the gate
    refused **fifteen consecutive slots with kafka sitting at a healthy 24 %**. The sweep only began
    working when the countdown had fallen far enough on its own, by which point pass 1 was gone.
    The arithmetic says this was not bad luck - at the registered 30 runs the gate needs kafka under
    ~13 %, and a freshly recycled kafka is 24-26 %, so **a three-pass sweep could not be started at
    all**.

    The fix is the one `PREREGISTRATION-T6.1.md` section 4 already named - *"a kafka recycle between
    passes is the documented remedy and is recorded as a continuity event"* - implemented rather
    than left to the operator: `recycler` runs between passes, and the countdown therefore spans
    **one pass**, which is the horizon the projection is now honest about. A `recycler` of `None`
    keeps the whole-job countdown, because a driver that does not recycle must not tell the gate
    that it did.

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
    # **Resuming numbers the slots as the whole sweep would have**: a resumed pass 2 of 3 prints
    # `[11/30]`, not `[1/20]`, because the record it joins is the thirty-slot one.
    done = len(ids) * (start_pass - 1)
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
    # **And when a whole catalog's worth refuses in a row, stop asking altogether.**
    #
    # `standing_refusal` stops the *retries* and keeps marching, which is right for a condition
    # one scenario's world can clear. It is wrong for one no scenario can. Arm B of dev sweep 12
    # left a closed incident wearing an open state (see `store.save_investigation_state`) and then
    # launched **nineteen consecutive refusals over two and a half hours**, settling 300s between
    # each, to be told the same sentence nineteen times. A catalog's worth of consecutive
    # non-scoring outcomes is that: not this scenario's world, but the world.
    #
    # The bound is `len(ids)` rather than a constant because it is that argument and not a taste:
    # every scenario in the catalog has now failed at least once with nothing in between. One
    # scored run resets it, so a sweep that is merely unlucky never reaches it - arm B's own pass 1
    # alternated five scored and five refused and would not have tripped this.
    unscored_in_a_row = 0

    result.start_pass = start_pass
    for pass_number in range(start_pass, repeats + 1):
        if recycler is not None:
            # **Before every pass, including the first**, never during one: the gate's projection
            # below assumes a pass begins on a cleared kafka, and until 2026-09-10 pass 1 was the
            # one pass that never got one. Arm B of dev sweep 12 started on the world arm A had
            # just spent ten hours filling - kafka at 69.7 % - and the gate refused five of the
            # first pass's ten slots on a forecast that was arithmetically right about a world
            # nobody had recycled. A driver that tells the gate "one pass' worth of growth" owes
            # it a pass that starts clear.
            where = (
                f"before pass {pass_number}"
                if pass_number == start_pass
                else f"between passes {pass_number - 1} and {pass_number}"
            )
            print(f"--- recycling the world {where}", flush=True)
            recycler()
        for index, scenario_id in enumerate(ids):
            done += 1
            # **The horizon the gate is told about, and why it is one pass.** With a recycler, kafka
            # is cleared between passes, so the growth this pass's runs can accumulate is bounded by
            # this pass. Without one, nothing clears it and the honest horizon is the whole job.
            remaining = len(ids) - index if recycler is not None else total - done + 1
            argv = [
                "faultline-eval",
                scenario_id,
                "--runs-remaining",
                str(remaining),
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
                unscored_in_a_row = 0
            else:
                unscored_in_a_row += 1
                if code in CLEARABLE and budget > 1:
                    standing_refusal = True
            result.outcomes.append(
                Outcome(scenario_id=scenario_id, exit_code=code, attempts=attempt)
            )
            print(f"=== {scenario_id}: {EXIT_NAMES.get(code, code)}", flush=True)

            if unscored_in_a_row >= len(ids):
                result.aborted = (
                    f"{unscored_in_a_row} scenarios in a row did not score - a whole catalog's "
                    f"worth, the last of them {EXIT_NAMES.get(code, code)}. The condition is in "
                    "the world, not in any one scenario; the remaining "
                    f"{total - done} slot(s) were not attempted."
                )
                print(f"\n*** ABORTING: {result.aborted}", flush=True)
                return result
    return result


def _shell(argv: list[str]) -> int:  # pragma: no cover - the subprocess path
    return subprocess.run(argv, check=False).returncode


RECYCLE_SETTLE_SECONDS = 300
"""What the baseline gate's own refusal says: *"Containers settle in 300s."* A recycle followed
immediately by a run trades one refusal for another."""


def _recycle_world() -> None:  # pragma: no cover - the subprocess path
    """kafka and the three consumers that never reconnect without it, then the settle.

    **Not a workaround - the documented remedy, run rather than printed.** T7.27 measured that
    kafka's consumers do not reconnect on their own, T7.30 measured the recycle clearing 99.87% to
    26.27%, and ADR-0005's T7.30 addendum records why raising the limit is not the answer: the
    growth is Rosetta translation cache, driven by work and not bounded by a ceiling. The gate has
    printed these exact two commands at every refusal since T7.29; `PREREGISTRATION-T6.1.md`
    section 4 registered them as a continuity event between passes. This is that, executed.
    """
    subprocess.run(["docker", "restart", "kafka"], check=False)
    time.sleep(20)
    subprocess.run(
        ["docker", "restart", "accounting-service", "frauddetection-service", "checkout-service"],
        check=False,
    )
    print(f"--- recycled; settling {RECYCLE_SETTLE_SECONDS}s before the next pass", flush=True)
    time.sleep(RECYCLE_SETTLE_SECONDS)


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
    p.add_argument(
        "--holdout",
        action="store_true",
        help="include the holdout scenarios, which are excluded by default. A holdout entry is a "
        "different experiment (ADR-0008 axis 1) and faultline-eval refuses one without its own "
        "--holdout, so before this flag existed a catalog sweep attempted three scenarios it "
        "could never run - and their place in --runs-remaining inflated the gate's projection",
    )
    p.add_argument("--baseline", choices=("b0", "b1", "b2"), default=None)
    p.add_argument(
        "--without",
        action="append",
        default=[],
        metavar="SPECIALIST",
        help="passed through to faultline-eval: withhold a specialist on every run (T6.1)",
    )
    p.add_argument("--postgres-dsn", default=None)
    p.add_argument(
        "--start-pass",
        type=int,
        default=1,
        metavar="N",
        help=(
            "resume a tier's sweep at pass N instead of pass 1. **For a sweep something outside "
            "the world stopped** - dev sweep 12's arm B completed pass 1 of 3 and then the API "
            "credit balance ran out, and the only way to finish it was thirty more runs, ten of "
            "them surplus. The manifests still declare the tier's R because that is still the "
            "design; the slots are numbered as the whole sweep's would be; the passes before N "
            "are your claim to have scored elsewhere, and the summary says so (default: 1)"
        ),
    )
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
    ids = runnable(holdout=args.holdout)

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
    for specialist in args.without:
        extra += ["--without", specialist]
    if args.holdout:
        extra += ["--holdout"]

    # **The declared repeat count and the number of passes are the same number.** A tier that
    # declared R = 3 while one pass ran would put a corrupt fingerprint on every run in the sweep.
    repeats = variance.TIERS[args.tier][0] if args.tier else 1
    if not 1 <= args.start_pass <= repeats:
        print(
            f"REFUSED: --start-pass {args.start_pass} is outside this tier's 1..{repeats} passes."
        )
        return 3
    passes = repeats - args.start_pass + 1
    estimate = len(ids) * passes
    resumed = f" (resuming at pass {args.start_pass} of {repeats})" if args.start_pass > 1 else ""
    print(
        f"{len(ids)} scenario(s) x {passes} pass(es) = {estimate} run(s){resumed}. "
        f"At the recorded median of ${MEDIAN_RUN_USD:.2f}/run that is about "
        f"${estimate * MEDIAN_RUN_USD:.0f}, and the measured discard rate is "
        f"{DISCARD_RATE:.0%} - budget about ${estimate * MEDIAN_RUN_USD / (1 - DISCARD_RATE):.0f}."
    )
    result = sweep(
        ids,
        repeats=repeats,
        extra=extra,
        settle=args.settle,
        retries=args.retries,
        recycler=_recycle_world if repeats > 1 else None,
        start_pass=args.start_pass,
    )
    result.declared_repeats = repeats
    print("\n".join(result.render()))
    return result.exit_code


def run_cli() -> None:  # pragma: no cover - console entry point
    raise SystemExit(main())
