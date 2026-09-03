"""The CI smoke subset, and what it may never be used for (T4.5).

The plan's T4.5: *"a small smoke subset on every change touching prompts/context/models; the full
catalog nightly with trend tracking."* Method: *"Smoke suite chosen for coverage per-minute;
nightly results appended to the eval DB; regression thresholds fail loudly; smoke results are
labeled non-citable in the CI output itself (R=1 is change detection, never a finding), so a smoke
number can't be screenshotted into a README six weeks later."*

## Coverage per minute, and why these four

**One scenario per fault class**, which is the most coverage a subset of this size can buy: the
four classes are the axis every accuracy figure is broken down by, and a smoke run that missed one
would be blind to a change that only hurts that class. Within each class the choice is the
scenario with the most recorded successful runs, because a smoke suite that fails for reasons of
its own teaches nothing and gets ignored within a fortnight.

`cart-bad-image-tag` is the exception and is chosen deliberately despite being **the scenario dev
sweep 8 got wrong**. A smoke suite made only of scenarios that pass is a suite that cannot detect
a regression on the hard one, and this is the hard one.

## Why R = 1 here is not a defect

Change detection, not measurement. Four scenarios at R = 1 has an MDE far larger than any effect
worth acting on - `evals/MDE.md` puts it near 45pp - so a smoke run **cannot** tell you a prompt
edit made the pipeline better or worse. What it can tell you is that the pipeline still completes
end to end on all four classes, which is what a pre-merge check is for.

## The non-citable label is machine-checked, not remembered

`NON_CITABLE` is printed in the CI output by the workflow and asserted by a test. The plan's
reason is exact: *"so a smoke number can't be screenshotted into a README six weeks later"*, and a
convention that lives only in a reviewer's memory is one that survives until the first person who
was not in the conversation.
"""

from __future__ import annotations

SMOKE_SCENARIOS: tuple[tuple[str, str, str], ...] = (
    (
        "ad-memory-squeeze",
        "resource_exhaustion",
        "the most-run scenario in the catalog and correct under every pipeline that scored it",
    ),
    (
        "cart-dependency-latency",
        "dependency_latency",
        "correct under every pipeline; also the ADR-0027 case where two remediations are right, "
        "so it exercises the scorer's dispute path as well as the agent",
    ),
    (
        "cart-redis-misconfig",
        "bad_config",
        "correct under every pipeline since S3, with the widest blast radius of the four - the "
        "one most likely to expose a triage or fan-out regression",
    ),
    (
        "cart-bad-image-tag",
        "bad_deploy",
        "**chosen because dev sweep 8 got it wrong.** A smoke suite made only of scenarios that "
        "pass cannot detect a regression on the hard one, and a suite that never fails is a "
        "suite nobody reads",
    ),
)
"""Four scenarios, one per fault class. `(scenario_id, fault_class, why)`."""

NON_CITABLE = (
    "SMOKE RESULT - NOT CITABLE. R=1 change detection only, never a finding. "
    "At n=4, R=1 this subset's MDE is ~44pp (evals/MDE.md): it cannot tell you whether a change "
    "helped or hurt, only whether the pipeline still completes. Any number from this run that "
    "reaches a README or a table is a misuse of it."
)
"""Printed by the smoke workflow and asserted by a test.

T4.5 asks for smoke results to be *"labeled non-citable in the CI output itself"*, and the
labelling has to be mechanical for the same reason the freeze is: a convention that lives in a
reviewer's memory survives exactly until the first person who was not in the conversation.
"""


def scenario_ids() -> list[str]:
    return [scenario for scenario, _, _ in SMOKE_SCENARIOS]


def classes_covered() -> set[str]:
    return {fault_class for _, fault_class, _ in SMOKE_SCENARIOS}
