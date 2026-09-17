"""T6.5 §4's two arms: the switch, what it derives, and what stops them pooling.

**The measurement had no implementation of its own independent variable.** `faultline-eval`
hardcoded `--exclude-origins <scenario_id>` into the `faultline-investigate` command, there was no
flag anywhere above it to widen that, and `faultline-sweep` passes a fixed set of flags through
which did not include one. Every run the harness could make was a WITH-arm run. The comma-splitting
in `investigation._exclusion_for` that T6.5 built had no caller.

Found before the sweep rather than during it, which is the only reason it cost nothing.
"""

from __future__ import annotations

from argparse import Namespace

import pytest

from evalharness.evaldb import FINGERPRINT_INPUTS
from evalharness.run import exclusion_for, exclusion_policy
from evalharness.sweep import UnknownScenarioError, runnable, same_class_origins

WITH = Namespace(exclude_same_class=False)
WITHOUT = Namespace(exclude_same_class=True)


def test_the_with_arm_excludes_the_scenarios_own_documents_and_nothing_else() -> None:
    """What every run made before T6.5 did, unchanged - so the arm that already existed keeps
    its behaviour and the new flag is the only thing that moves it."""
    assert exclusion_for("cart-redis-misconfig", WITH) == ["scenario:cart-redis-misconfig"]


def test_the_without_arm_excludes_every_runnable_scenario_of_the_class() -> None:
    """§4: *"S's own documents, and every other dev scenario in C"*. `cart-redis-misconfig` is
    `bad_config`, which has four runnable dev scenarios."""
    assert exclusion_for("cart-redis-misconfig", WITHOUT) == [
        "scenario:cart-redis-misconfig",
        "scenario:payment-telemetry-blackout",
        "scenario:product-catalog-flag-failure",
        "scenario:shipping-quote-misconfig",
    ]


def test_the_without_arm_always_contains_the_with_arm() -> None:
    """Both arms exclude S's own documents - T4.1b already did, and it is not what is being
    measured. A WITHOUT arm that dropped that would be measuring two things at once."""
    for scenario in runnable():
        assert set(exclusion_for(scenario, WITH)) <= set(exclusion_for(scenario, WITHOUT))


def test_the_arms_differ_for_every_runnable_scenario() -> None:
    """**A scenario alone in its class would make the two arms identical**, and a run of it would
    be scored into the WITHOUT column while being a WITH run. There is no such scenario today;
    this fails on the commit that adds one."""
    for scenario in runnable():
        assert exclusion_for(scenario, WITH) != exclusion_for(scenario, WITHOUT), (
            f"{scenario} is alone in its fault class, so its two arms are the same run"
        )


def test_the_dose_is_not_the_same_in_every_class_which_the_report_has_to_say() -> None:
    """`bad_config` has four runnable scenarios and the other three classes have two, so the
    WITHOUT arm removes three other scenarios for a `bad_config` run and one for the rest.

    Not a defect - it is what §4 registered, read literally - but it means the arms differ by
    different amounts across classes, and a difference reported as one effect is an average over
    two doses. Pinned so the number is stated rather than discovered."""
    sizes = {s: len(exclusion_for(s, WITHOUT)) for s in runnable()}

    assert sorted(set(sizes.values())) == [2, 4]
    assert sum(1 for n in sizes.values() if n == 4) == 4, "the four bad_config scenarios"


def test_an_exclusion_is_stated_in_origins_so_it_removes_a_postmortem_too() -> None:
    """A postmortem is `postmortem:S` by `document_id` and `scenario:S` by `origin`. An exclusion
    stated in origins removes a scenario's postmortem with its narrative, knowing nothing about
    postmortems - which is why the arm is expressed this way and not as a document list."""
    assert all(
        origin.startswith("scenario:") for origin in exclusion_for("ad-memory-squeeze", WITHOUT)
    )


def test_a_scenario_outside_the_catalog_refuses_rather_than_returning_an_empty_arm() -> None:
    """An empty exclusion is a WITH-arm run with no exclusion at all - strictly worse than both
    arms - so a typo has to fail loudly rather than produce a run that looks scored."""
    with pytest.raises(UnknownScenarioError, match="not in the catalog"):
        same_class_origins("no-such-scenario")


def test_the_policy_and_not_the_resolved_list_is_what_the_fingerprint_sees() -> None:
    """**Both halves matter.** Without `exclusion_policy` the two arms share an `eval_configs`
    row and the experiment pools with its control on the axis it varies. With the resolved
    *list* instead, every scenario would get its own row and the table would group nothing."""
    assert "exclusion_policy" in FINGERPRINT_INPUTS
    assert "exclude_origins" not in FINGERPRINT_INPUTS

    assert exclusion_policy(WITH) == "own"
    assert exclusion_policy(WITHOUT) == "own+class"


def test_an_absent_flag_reads_as_the_with_arm_rather_than_raising() -> None:
    """`faultline-investigate` and the baselines construct their own namespaces. A missing
    attribute means nobody asked for the wider arm, which is the pre-T6.5 behaviour."""
    assert exclusion_policy(Namespace()) == "own"
    assert exclusion_for("cart-bad-image-tag", Namespace()) == ["scenario:cart-bad-image-tag"]


def test_the_sweep_can_actually_express_the_arm() -> None:
    """The gap that made this file necessary: the flag exists on `faultline-eval` and the sweep
    passes a fixed allowlist through. A flag the sweep cannot forward is a flag no sweep uses."""
    from evalharness.sweep import parser

    flags = {a.option_strings[0] for a in parser()._actions if a.option_strings}

    assert "--exclude-same-class" in flags


# --- the seam, which none of the above crossed -------------------------------------------------


def test_the_harness_side_and_the_agent_side_agree_on_what_an_origin_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Every test above passed while every run was INVALID.** They tested `exclusion_for` in
    isolation; the string it produced then crossed into `faultline-investigate`, whose
    `_exclusion_for` had always added `scenario:` to a bare id, and became
    `scenario:scenario:ad-memory-squeeze` - an origin nothing carries, so the exclusion removed
    nothing, so T4.1b marked the run INVALID. Found 2026-09-17 in the manifest of the first run
    that completed after #344, not by any test.

    So this test does what none of them did: it takes what the harness emits, hands it across
    the same boundary a real run crosses, and asserts what comes out is exactly the set of
    origins the corpus filters on.
    """
    from faultline.agents.investigation import Investigation

    for scenario in runnable():
        for args in (WITH, WITHOUT):
            emitted = exclusion_for(scenario, args)
            monkeypatch.setenv("FAULTLINE_EVAL_SCENARIO", ",".join(emitted))

            parsed = Investigation._exclusion_for("any-incident")

            assert parsed == frozenset(emitted), f"{scenario}: {sorted(parsed)} != {emitted}"
            assert all(o.count("scenario:") == 1 for o in parsed), "no origin is prefixed twice"


def test_the_agent_side_accepts_the_bare_id_every_recorded_sweep_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backwards: every sweep before #344 passed `--exclude-origins <id>` with no prefix, and
    the archive's `trajectory_retrievals` rows say `scenario:<id>`. That spelling still works."""
    from faultline.agents.investigation import Investigation, as_origin

    monkeypatch.setenv("FAULTLINE_EVAL_SCENARIO", "ad-memory-squeeze, cart-bad-image-tag")

    assert Investigation._exclusion_for("x") == frozenset(
        {"scenario:ad-memory-squeeze", "scenario:cart-bad-image-tag"}
    )
    assert as_origin("scenario:ad-memory-squeeze") == as_origin("ad-memory-squeeze")
    assert as_origin(as_origin("x")) == as_origin("x"), "idempotent"
