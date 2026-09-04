"""The catalog driver Gate 4's first condition names (T4.1 / G4).

*"`make eval` injects, runs, scores, and reports all 10 scenarios unattended."* `faultline-eval`
takes one scenario; the only thing that ever ran a catalog was a shell loop inside a GitHub
Actions workflow — CI-only, untested, and unreachable from a terminal. `docs/GATES.md` has listed
that as a G4 blocker since before the Phase 4 audit.
"""

from __future__ import annotations

from evalharness import sweep


def recorder(codes: dict[str, int]) -> tuple[list[list[str]], object]:
    """A runner that answers with a fixed exit code per scenario and records every argv."""
    seen: list[list[str]] = []

    def run(argv: list[str]) -> int:
        seen.append(argv)
        return codes.get(argv[1], 0)

    return seen, run


# --- the countdown is the whole reason this is not a for-loop in bash --------------------------


def test_runs_remaining_counts_down_from_the_catalog_size() -> None:
    """**The baseline gate projects the world's memory over the work still to come** and refuses a
    sweep at its start rather than partway through (T7.32). A driver passing `--single-run` per
    scenario would defeat that; one passing a constant would let the projection drift as the
    sweep progressed."""
    seen, run = recorder({})

    sweep.sweep(["a", "b", "c"], runner=run)

    assert [argv[argv.index("--runs-remaining") + 1] for argv in seen] == ["3", "2", "1"]


def test_every_scenario_is_launched_through_the_cli_and_not_imported() -> None:
    """ADR-0004 keeps the harness outside the product: it drives `faultline-eval` and reads its
    **exit code**. A driver that imported `run.main` would be a second harness with its own
    subtly different behaviour."""
    seen, run = recorder({})

    sweep.sweep(["a", "b"], runner=run)

    assert [argv[0] for argv in seen] == ["faultline-eval", "faultline-eval"]
    assert [argv[1] for argv in seen] == ["a", "b"]


def test_extra_flags_are_passed_through_to_every_run() -> None:
    seen, run = recorder({})

    sweep.sweep(["a"], extra=["--tier", "weekly"], runner=run)

    assert seen[0][-2:] == ["--tier", "weekly"]


# --- a discard must not end the sweep ------------------------------------------------------------


def test_a_discarded_scenario_does_not_stop_the_ones_after_it() -> None:
    """**32% of every run ever started has been discarded**, so this is the common case rather
    than the edge one. A sweep that stopped at the first failure would report the catalog it got
    through while looking exactly like a catalog run."""
    seen, run = recorder({"b": 4})

    result = sweep.sweep(["a", "b", "c"], runner=run)

    assert len(seen) == 3, "c ran"
    assert result.scored == 2
    assert [o.name for o in result.outcomes] == ["scored", "discarded", "scored"]


def test_a_partial_catalog_is_not_a_pass() -> None:
    """**Not "nothing crashed".** A sweep where half the catalog was discarded ran perfectly and
    produced half a measurement; exiting 0 on it would let CI and a reader take a partial catalog
    for a whole one."""
    _, run = recorder({"b": 4})

    assert sweep.sweep(["a", "b"], runner=run).exit_code == 1
    _, clean = recorder({})
    assert sweep.sweep(["a", "b"], runner=clean).exit_code == 0


def test_an_empty_sweep_is_a_failure_and_not_a_vacuous_pass() -> None:
    """`all([])` is True and this repository has shipped that defect twice - in `RankedScore` and
    in `aa.Result`. A sweep of nothing scored nothing."""
    assert sweep.SweepResult().exit_code == 1


def test_the_summary_says_which_scenarios_did_not_score_and_why() -> None:
    """A count alone tells a reader that something went wrong and not what. The exit codes are
    four distinct outcomes precisely so they need not be pooled at the last step."""
    _, run = recorder({"b": 4, "c": 3})
    rendered = "\n".join(sweep.sweep(["a", "b", "c"], runner=run).render())

    assert "1/3 scored" in rendered
    assert "b" in rendered and "discarded" in rendered
    assert "c" in rendered and "gate refused" in rendered
    assert "not a score" in rendered, "a sweep summary must not read as a result"


def test_every_exit_code_the_harness_can_return_has_a_name() -> None:
    """**The codes were prose in an argparse epilog and bare integers at the return sites**, which
    is fine until something has to *interpret* one. This driver does, so they are a table now, and
    a second hand-written copy is how a driver comes to print `exit 6` for a run the harness
    calls INVALID."""
    from evalharness.run import EXIT_CODES, exit_codes_epilog

    assert set(EXIT_CODES) <= set(sweep.EXIT_NAMES), "a code the summary cannot name"
    # The help text is generated from the table, so it cannot describe a different contract.
    epilog = exit_codes_epilog()
    for code in EXIT_CODES:
        assert f"{code} " in epilog


# --- what is runnable, and what is deliberately not ----------------------------------------------


def test_a_scenario_whose_bundle_is_invalid_is_not_runnable(tmp_path: object) -> None:
    """`currency-cpu-throttle` and `flag-service-crashloop` produced nothing observable. Including
    them would put two guaranteed failures in every sweep and **quietly lower every rate this
    harness prints** with nothing about the pipeline having changed."""
    ids = sweep.runnable()

    assert ids, "the catalog is not empty"
    assert "currency-cpu-throttle" not in ids
    assert "flag-service-crashloop" not in ids
    assert ids == sorted(ids), "a stable order, so two sweeps are comparable"


def test_the_driver_is_reachable_as_a_command() -> None:
    """**The defect this file exists to close.** The catalog loop lived in a workflow's `run:`
    block: real, working, and invocable only by GitHub. A capability nothing at a terminal can
    reach is one nobody can rehearse before a gate."""
    import tomllib
    from pathlib import Path

    manifest = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())

    assert manifest["project"]["scripts"]["faultline-sweep"] == "evalharness.sweep:run_cli"


def test_listing_makes_no_run() -> None:
    assert sweep.main(["--list"]) == 0


# --- the tier declares a repeat count, so the sweep must actually repeat -------------------------


def test_a_tier_that_declares_three_repeats_runs_the_catalog_three_times() -> None:
    """**The defect this driver shipped with, caught before it cost anything.**

    `faultline-eval --tier weekly` writes `repeat_count = 3` into the manifest and runs **once** -
    nothing in it repeats. A driver that passed the tier through and made a single pass would have
    produced a catalog of runs each *declaring* R = 3 while R = 1 actually happened: a corrupt
    fingerprint on every run, and exactly the "declared R and observed runs per scenario differ"
    mismatch `compare.report` warns about. The declared count and the number of passes are now the
    same number by construction.
    """
    seen, run = recorder({})

    result = sweep.sweep(["a", "b"], repeats=3, runner=run)

    assert len(seen) == 6, "two scenarios, three passes"
    assert len(result.outcomes) == 6


def test_the_countdown_spans_the_whole_job_and_not_one_pass() -> None:
    """The baseline gate projects the world's memory over the work still to come. A countdown that
    reset each pass would tell it the sweep was a third of its real length, and it would admit a
    job it should have refused at the start (T7.32)."""
    seen, run = recorder({})

    sweep.sweep(["a", "b"], repeats=3, runner=run)

    assert [argv[argv.index("--runs-remaining") + 1] for argv in seen] == list("654321")


def test_every_scenario_runs_once_before_any_scenario_runs_twice() -> None:
    """**Catalog-major, not scenario-major.** Three repeats of one scenario back to back would
    measure it against three nearly identical world states and understate run-to-run variance -
    the one quantity R > 1 exists to estimate."""
    seen, run = recorder({})

    sweep.sweep(["a", "b", "c"], repeats=2, runner=run)

    assert [argv[1] for argv in seen] == ["a", "b", "c", "a", "b", "c"]


def test_the_cost_of_the_job_is_printed_before_it_starts() -> None:
    """CLAUDE.md rule 8. An operator about to spend an hour of world time and real money should see
    the number first, and it is measured rather than guessed: median $0.53 over 87 recorded runs,
    inflated by the 33% discard rate because a sweep pays for the runs it *starts*."""
    assert sweep.MEDIAN_RUN_USD == 0.53
    assert 0.3 < sweep.DISCARD_RATE < 0.4

    import inspect

    source = inspect.getsource(sweep.main)
    assert "MEDIAN_RUN_USD" in source and "DISCARD_RATE" in source


# --- a pre-registered scope is a commitment, not a default ---------------------------------------


def test_only_selects_exactly_the_named_scenarios_in_the_order_given() -> None:
    """**`evals/runs/PREREGISTRATION-2026-09-03-top3.md` registers five scenarios, one run each.**
    A registration written before the fact is a commitment to a scope; running the catalog instead
    would be a different experiment, and the whole value of registering is that the scope cannot
    move once the balance is in view."""
    five = sweep.runnable()[:5]

    assert sweep.select(sweep.runnable(), ",".join(five)) == five
    assert sweep.select(["a", "b", "c"], "c, a") == ["c", "a"], "the order it names them"


def test_an_unrunnable_id_is_refused_rather_than_skipped() -> None:
    """**Refused, never silently narrowed.** A scope that quietly dropped a scenario would produce
    a sweep whose document claims five and whose record holds four, and the discrepancy would
    surface as an unexplained `n` weeks later - the shape of every stale number this repository has
    had to correct."""
    import pytest

    with pytest.raises(sweep.UnknownScenarioError) as refusal:
        sweep.select(["ad-memory-squeeze"], "ad-memory-squeeze,not-a-scenario")

    assert "not-a-scenario" in str(refusal.value)
    assert "Runnable:" in str(refusal.value), "and it says what it would have accepted"


def test_the_scope_parser_is_a_function_nothing_has_to_run_to_test() -> None:
    """**The defect this file shipped with, for about four minutes.**

    The first version parsed `--only` inside `main()`, so the only way to exercise it was to call
    `main()` - which uses the real shell runner and launched actual `faultline-eval` subprocesses.
    Running the test suite created six run directories, and on a machine with a live world it
    would have injected faults. A parser that can only be tested by running the thing it
    configures is not a parser anybody can test.
    """
    import ast
    import inspect
    import textwrap

    assert "select(" in inspect.getsource(sweep.main), "main delegates rather than parsing inline"

    # **Over the AST, not the source text.** The first version asserted `"subprocess" not in
    # inspect.getsource(sweep.select)` and failed on `select`'s own docstring, which explains the
    # subprocess bug - the eighth time in this repository that a fragment of English has been
    # mistaken for a property. `tests/test_allowlist.py` already solved this shape: parse the
    # function and look at what it *calls*, "docstrings excluded, since prose may name what code
    # must not do" (ADR-0032).
    tree = ast.parse(textwrap.dedent(inspect.getsource(sweep.select)))
    names = {
        node.id if isinstance(node, ast.Name) else node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Name | ast.Attribute)
    }

    assert not names & {"subprocess", "run", "_shell", "sweep", "Popen"}, (
        f"select reaches something that executes: {sorted(names & {'subprocess', 'run', '_shell'})}"
    )


def test_a_named_scope_still_honours_its_tier() -> None:
    """Scope and repeat count are independent: a registration may name five scenarios at R=3 as
    easily as at R=1."""
    seen, run = recorder({})

    sweep.sweep(sweep.select(["a", "b", "c"], "a,b"), repeats=2, runner=run)

    assert [argv[1] for argv in seen] == ["a", "b", "a", "b"]


# --- runs cannot go back to back, and the first real sweep proved it -----------------------------


def waiter() -> tuple[list[float], object]:
    naps: list[float] = []

    def sleep(seconds: float) -> None:
        naps.append(seconds)

    return naps, sleep


def test_a_run_that_injected_is_followed_by_a_settle_wait() -> None:
    """**The defect the first real B0 sweep found.** It scored scenario 1 and the gate refused 2
    through 5: *"incident … resolved at … and is still inside the orchestrator's 300s settle
    window - a firing episode now would reopen it rather than open a new incident, and this run's
    alerts would be attributed to the previous one."*

    The gate was right and the driver was wrong. Every scored run leaves a resolved incident that
    blocks the next for five minutes, so a sweep running back to back can only ever score its
    first scenario.
    """
    _, run = recorder({})
    naps, sleep = waiter()

    sweep.sweep(["a", "b", "c"], runner=run, settle=300, sleeper=sleep)

    assert naps == [300, 300], "after a and after b, not before a"


def test_nothing_is_waited_for_until_something_has_been_injected() -> None:
    """A sweep whose first scenarios all refuse has broken nothing, and should not sit idle for
    five minutes apiece waiting for a world it never touched to settle."""
    _, run = recorder({"a": 3, "b": 3})
    naps, sleep = waiter()

    sweep.sweep(["a", "b", "c"], runner=run, settle=300, retries=1, sleeper=sleep)

    assert naps == [], "a and b injected nothing; c is the first run, so nothing to settle from"


def test_a_refused_scenario_is_relaunched_because_nothing_was_injected() -> None:
    """**Not a re-run.** The harness's own refusal says *"nothing was injected and this scenario
    has not been attempted"*, so there is no run to repeat - which matters, because ADR-0022
    section 3.3 forbids re-running a *scored* run to improve a number and that rule must not be
    read as forbidding this."""
    attempts = {"n": 0}

    def flaky(argv: list[str]) -> int:
        attempts["n"] += 1
        return 3 if attempts["n"] < 3 else 0  # refused twice, then the world is ready

    naps, sleep = waiter()
    result = sweep.sweep(["a"], runner=flaky, retries=6, sleeper=sleep)

    assert attempts["n"] == 3
    assert result.outcomes[0].scored is True
    assert result.outcomes[0].attempts == 3
    assert naps == [sweep.RETRY_WAIT_SECONDS, sweep.RETRY_WAIT_SECONDS]


def test_a_discarded_run_is_never_relaunched() -> None:
    """**A discard means the fault was injected and the run happened.** Relaunching it would be a
    second attempt at a scored measurement, which is exactly the thing ADR-0022 section 3.3
    forbids - and the difference between that and retrying a refusal is whether the world was
    touched."""
    attempts = {"n": 0}

    def discards(argv: list[str]) -> int:
        attempts["n"] += 1
        return 4

    naps, sleep = waiter()
    result = sweep.sweep(["a"], runner=discards, retries=6, sleeper=sleep)

    assert attempts["n"] == 1, "once, and recorded"
    assert result.outcomes[0].name == "discarded"
    assert naps == []


def test_retries_are_bounded_so_an_unclearable_refusal_ends() -> None:
    """A gate refusal can be unclearable - the orchestrator down, the world unhealthy. Retrying
    forever would turn a sweep into a hang, and the operator would learn nothing they could not
    have learned from the first refusal."""
    _naps, sleep = waiter()
    _, run = recorder({"a": 3})

    result = sweep.sweep(["a"], runner=run, retries=3, sleeper=sleep)

    assert result.outcomes[0].attempts == 3
    assert result.outcomes[0].name == "gate refused"


def test_the_library_function_does_not_sleep_by_default() -> None:
    """**The second defect in this commit.** `settle` and `retries` first defaulted to the real
    300s and 6, and the suite hung: every existing test called `sweep()` without a sleeper and
    tried to nap for twenty minutes. Waiting is a property of running against a live world, which
    is `main()`'s job - a library function whose default behaviour is to sleep is one nobody can
    call in a test without knowing to disarm it."""
    import inspect

    parameters = inspect.signature(sweep.sweep).parameters

    assert parameters["settle"].default == 0
    assert parameters["retries"].default == 1
