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
