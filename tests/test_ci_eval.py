"""T4.5's world-free half: the guards that run on every push, and the smoke suite's own shape.

The eval workflows need a world and an API key; these need neither. They are the layer that
catches the mistakes a smoke run would catch **before** the smoke run can be afforded, plus the
assertions that keep the smoke suite honest about what it is.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from evalharness import smoke, sweep

WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"
SCENARIOS = Path(__file__).parent.parent / "evals" / "scenarios"


def workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / f"{name}.yml").read_text())


# --- the smoke subset ------------------------------------------------------------------------


def test_the_smoke_subset_covers_every_fault_class() -> None:
    """**"Coverage per minute", made checkable.** The four classes are the axis every accuracy
    figure is broken down by, so a subset missing one is blind to a change that only hurts that
    class - and would be blind silently."""
    from evalharness.scenario import load_catalog

    catalog = [s for s in load_catalog(SCENARIOS) if "examples" not in str(s.id)]
    classes = {s.fault_class for s in catalog}

    assert smoke.classes_covered() == classes, (
        f"the smoke suite covers {smoke.classes_covered()} and the catalog has {classes}"
    )


def test_every_smoke_scenario_exists_and_is_runnable() -> None:
    """A smoke suite naming a scenario that was renamed, or one carrying INVALID.md, fails in CI
    for a reason that has nothing to do with the change under test - and gets ignored."""
    from evalharness.scenario import load_catalog

    known = {s.id for s in load_catalog(SCENARIOS)}
    for scenario_id in smoke.scenario_ids():
        assert scenario_id in known, f"{scenario_id} is not in the catalog"
        invalid = [
            SCENARIOS / "artifacts" / split / scenario_id / "INVALID.md"
            for split in ("dev", "holdout")
        ]
        assert not any(path.is_file() for path in invalid), (
            f"{scenario_id} carries INVALID.md and cannot be run"
        )


def test_every_smoke_scenario_states_why_it_is_in_the_suite() -> None:
    """A subset without stated selection reasoning is a subset nobody can argue with, and the
    first person to add a fifth scenario has no rule to follow."""
    for scenario_id, fault_class, why in smoke.SMOKE_SCENARIOS:
        assert why.strip(), scenario_id
        assert fault_class.strip(), scenario_id


def test_the_smoke_suite_includes_a_scenario_that_has_failed() -> None:
    """**The selection rule that matters.** A suite made only of scenarios that pass cannot
    detect a regression on the hard one. `cart-bad-image-tag` is in the suite precisely because
    dev sweep 8 returned the wrong class for it."""
    assert "cart-bad-image-tag" in smoke.scenario_ids()


# --- the non-citable label -------------------------------------------------------------------


def test_the_smoke_result_is_labelled_non_citable_and_says_why() -> None:
    """T4.5: *"smoke results are labeled non-citable in the CI output itself (R=1 is change
    detection, never a finding), so a smoke number can't be screenshotted into a README six weeks
    later."* The label has to be mechanical for the same reason the freeze is."""
    assert "NOT CITABLE" in smoke.NON_CITABLE
    assert "R=1" in smoke.NON_CITABLE
    assert "MDE" in smoke.NON_CITABLE, "the label must say why, not merely that"


def test_the_smoke_workflow_prints_the_label_whenever_a_run_happened() -> None:
    """The label must survive a failed *run* - a partial smoke result is exactly the kind that
    gets quoted - but must not fire when there is nothing to label.

    The condition tightened from `!= 'skipped'` to `== 'success'` when the first boot failure
    showed that a failed boot is not skipped either. A label on a sweep that never started
    labels nothing, the same argument one state further along; a sweep that started and scored
    two of four still gets labelled, because `always()` covers the sweep step's own failure.
    """
    steps = workflow("eval-smoke")["jobs"]["smoke"]["steps"]
    printing = [s for s in steps if "NON_CITABLE" in str(s.get("run", ""))]

    assert printing, "the smoke workflow must print the non-citable label"
    condition = printing[0].get("if", "")
    assert "always()" in condition
    assert "steps.boot.outcome == 'success'" in condition


def test_no_cleanup_step_runs_when_the_world_was_never_booted() -> None:
    """**Found by the first red run.** The key check refused before anything started, and every
    `always()` step ran anyway: the database load reached for a Postgres that was never booted
    and failed a second time with an error about a database, when the real answer was "there is
    no key". An unconditional artifact upload would also have shipped all 128 committed run
    directories on a refusal.

    Every step that runs after a failure is now conditioned on the boot step having actually run,
    so a refusal produces one clear failure instead of a cascade.
    """
    for name, job in (("eval-smoke", "smoke"), ("eval-nightly", "nightly")):
        steps = workflow(name)["jobs"][job]["steps"]
        boot = [s for s in steps if s.get("id") == "boot"]
        assert boot, f"{name} must give its boot step an id for the cleanup steps to reference"

        for step in steps:
            condition = str(step.get("if", ""))
            if "always()" not in condition:
                continue
            assert "steps.boot.outcome" in condition, (
                f"{name}: {step.get('name') or step.get('uses')} runs unconditionally after a "
                "refusal, when nothing was started"
            )


def test_a_step_that_consumes_the_boot_requires_the_boot_to_have_succeeded() -> None:
    """**`!= 'skipped'` was wrong one state later than `always()` was.**

    The refusal case was fixed and the failure case was not: a boot that *fails* is not
    `'skipped'` either. So the first real boot failure - kafka unhealthy eight seconds in -
    produced two errors, a dependency failure and a database error from a load that should never
    have started, and the second one is the kind that sends a reader looking at Postgres.

    A step that reads what the boot produced needs the boot to have **succeeded**. `Tear down` is
    the one exception, and deliberately: cleaning up after a half-started world is exactly when
    cleanup matters.
    """
    for name, job in (("eval-smoke", "smoke"), ("eval-nightly", "nightly")):
        for step in workflow(name)["jobs"][job]["steps"]:
            label = str(step.get("name") or step.get("uses"))
            condition = str(step.get("if", ""))
            if "always()" not in condition:
                continue
            if label == "Tear down":
                assert "!= 'skipped'" in condition, "cleanup must survive a half-started world"
                continue
            assert "== 'success'" in condition, (
                f"{name}: {label} runs after a failed boot and consumes what the boot makes"
            )


def test_a_failed_boot_captures_why_before_the_teardown_removes_it() -> None:
    """**The first boot failure took its own evidence with it.** Kafka went unhealthy, the boot
    failed on the dependency, `Tear down` removed the container, and the run that would say why
    produced nothing to read - so diagnosing it would have meant failing again.

    This is ADR-0022 §3.3's rule applied one level out: a run that produced no result is recorded
    with its reason rather than deleted. A boot that fails is the same kind of event, and it
    costs nothing to capture because it happens before the first model call.
    """
    for name, job in (("eval-smoke", "smoke"), ("eval-nightly", "nightly")):
        steps = workflow(name)["jobs"][job]["steps"]
        names = [str(s.get("name") or s.get("uses")) for s in steps]
        diagnostic = [s for s in steps if "docker ps -a" in str(s.get("run", ""))]

        assert diagnostic, f"{name} discards the reason its world did not come up"
        assert "steps.boot.outcome == 'failure'" in str(diagnostic[0]["if"])
        assert "logs" in str(diagnostic[0]["run"]), "container logs, not only a process list"
        assert names.index(str(diagnostic[0]["name"])) < names.index("Tear down"), (
            f"{name}: the diagnostic runs after the teardown that deletes what it would read"
        )


# --- the workflows themselves -----------------------------------------------------------------


def test_the_smoke_workflow_triggers_on_prompt_context_and_model_paths() -> None:
    """The plan's trigger: *"every change touching prompts/context/models"*."""
    paths = workflow("eval-smoke")[True]["pull_request"]["paths"]

    assert "src/faultline/agents/roles.py" in paths, "prompts"
    assert "src/faultline/agents/contracts.py" in paths, "the schemas prompts promise"
    assert any(p.startswith("src/faultline/context/") for p in paths), "context"
    assert "src/faultline/agents/settings.py" in paths, "the model map"


def test_the_nightly_runs_on_a_schedule_and_the_smoke_does_not() -> None:
    assert "schedule" in workflow("eval-nightly")[True]
    assert "schedule" not in workflow("eval-smoke")[True]


def test_both_eval_workflows_refuse_before_booting_the_world_when_there_is_no_key() -> None:
    """Q20's finding, applied here before it can happen: booting a fifteen-service stack to
    discover the model is unreachable is the harness defect this project already recorded."""
    for name, job in (("eval-smoke", "smoke"), ("eval-nightly", "nightly")):
        steps = workflow(name)["jobs"][job]["steps"]
        names = [str(s.get("name", "")) for s in steps]
        refuse = next(i for i, n in enumerate(names) if "Refuse early" in n)
        boot = next(i for i, n in enumerate(names) if "Bring up" in n)
        assert refuse < boot, f"{name} boots the world before checking for a key"


def test_both_eval_workflows_share_one_world_lock() -> None:
    """One world, one stack. Two runs at once would inject into the same services, which is the
    condition the harness's own world lock refuses - better queued here than discarded there."""
    assert workflow("eval-smoke")["concurrency"]["group"] == "eval-world"
    assert workflow("eval-nightly")["concurrency"]["group"] == "eval-world"


def test_the_nightly_does_not_stop_at_the_first_discard() -> None:
    """Every outcome is a row (T4.4). A catalog run that halted on the first failure would report
    the catalog it got through, which is a different and flattering catalog."""
    steps = workflow("eval-nightly")["jobs"]["nightly"]["steps"]
    catalog = next(s for s in steps if s.get("name") == "The catalog")

    assert "|| true" in catalog["run"]


def test_both_eval_workflows_append_to_the_eval_database() -> None:
    """T4.5: *"nightly results appended to the eval DB"*. Without this the trend line has no
    rows and `faultline-compare` has nothing to read."""
    for name, job in (("eval-smoke", "smoke"), ("eval-nightly", "nightly")):
        runs = " ".join(str(s.get("run", "")) for s in workflow(name)["jobs"][job]["steps"])
        assert "faultline-eval-db load" in runs, name


def test_the_required_checks_are_still_only_the_world_free_ones() -> None:
    """**The honest arrangement, asserted so it stays honest.** The eval workflows cannot pass
    without a world and a funded key, so they are separate workflows rather than jobs inside
    `ci`, and `ci` remains the thing a pull request waits on. If someone later makes them
    required, this test is where they will find out that they also made every PR wait on a
    fifteen-service stack and a live API."""
    ci = workflow("ci")

    assert set(ci["jobs"]) == {"checks", "docker", "integration"}
    for job in ci["jobs"].values():
        runs = " ".join(str(s.get("run", "")) for s in job["steps"])
        assert "faultline-eval " not in runs, "ci must not inject faults"


# --- neither workflow may hand-roll a catalog loop (T4.5) --------------------------------------


def test_no_eval_workflow_drives_faultline_eval_directly() -> None:
    """**The smoke workflow kept the loop the nightly shed, and it could not have passed.**

    Four `faultline-eval` calls back to back under `set -e`, with no wait between them: every
    scored run leaves a resolved incident, and a firing inside the orchestrator's 300-second
    window reopens it rather than opening a new one. Scenario 1 scores, scenario 2 is refused
    with exit 3, and the job ends there having already spent money. That is not a hypothetical -
    the first real sweep scored 1 of 5 before `faultline-sweep` learned to wait.

    The countdown, the settle, the retry and the "a discard must not end the run" rule all live
    in `faultline-sweep` with tests behind them. A workflow that calls `faultline-eval` in a shell
    loop is a second, untested copy of that logic reachable only by GitHub.
    """
    for name, job in (("eval-smoke", "smoke"), ("eval-nightly", "nightly")):
        for step in workflow(name)["jobs"][job]["steps"]:
            script = str(step.get("run", ""))
            if "faultline-eval " not in script:
                continue
            assert "faultline-sweep" in script, (
                f"{name}: {step.get('name')} drives faultline-eval directly; use faultline-sweep"
            )


def test_the_smoke_scope_is_read_from_the_module_not_restated() -> None:
    """`smoke.SMOKE_SCENARIOS` is the single source of truth for which four scenarios these are.
    A workflow listing them itself is a second list that goes stale silently - and the scenario
    ids would be the easiest thing in the world to quietly edit to dodge a failing one."""
    steps = workflow("eval-smoke")["jobs"]["smoke"]["steps"]
    running = [s for s in steps if "faultline-sweep" in str(s.get("run", ""))]

    assert running, "the smoke workflow must run the sweep"
    script = str(running[0]["run"])
    assert "smoke.scenario_ids()" in script
    for scenario_id in smoke.scenario_ids():
        assert scenario_id not in script, f"{scenario_id} is hard-coded in the workflow"


def test_the_smoke_run_does_not_swallow_its_own_failure() -> None:
    """The nightly carries `|| true` because a partial catalog still has something to load and
    label. A pre-merge smoke that did not complete its four is a failed check, and that is the
    entire point of it being one."""
    steps = workflow("eval-smoke")["jobs"]["smoke"]["steps"]
    script = next(str(s["run"]) for s in steps if "faultline-sweep" in str(s.get("run", "")))

    assert "|| true" not in script


def test_the_timeout_clears_the_settle_windows_it_now_honours() -> None:
    """Three 300-second waits between four scenarios is fifteen minutes of deliberate idling
    before a single model call. A smoke run killed by its own timeout is indistinguishable from a
    pipeline that hung, which is the worst possible failure for a change-detection check."""
    job = workflow("eval-smoke")["jobs"]["smoke"]
    settles = (len(smoke.SMOKE_SCENARIOS) - 1) * (sweep.SETTLE_SECONDS / 60)

    assert job["timeout-minutes"] > settles * 2, (
        "the timeout must leave room for the runs themselves, not only for the waits"
    )
