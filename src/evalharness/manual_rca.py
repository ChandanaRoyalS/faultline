"""The manual-RCA reference: the MTTR claim's missing left-hand side (T4.7).

T4.7's third deliverable: *"The MTTR claim gets its missing left-hand side the honest way:
self-timed manual RCA on five dev scenarios, reported as **n=5, self-timed, indicative** — an
unsourced number next to a rigorously sourced one damages the rigorous one."*

Every latency figure this repository produces is a time for the *pipeline*. Saying it is fast
requires something to be fast **against**, and until there is one, "three minutes to a report" is
a number with no denominator.

## The problem this deliverable has, which is not the plan's fault

**The only person available to do the manual RCA wrote the scenarios.**

She authored every fault, every injection, and every recorded narrative in this catalog. Timing
her investigating `ad-memory-squeeze` does not measure how long it takes a responder to find an
OOM-killed container. It measures **how long it takes someone who already knows the answer to
confirm it**, which is a different quantity and a much smaller one.

There is no fix available inside this project. A second person is not available; a holdout
scenario does not help, because she authored those too; and waiting for forgetting is not a
method. So the deliverable is produced with the contamination **stated at least as prominently as
the number**, which is what `CONTAMINATION` is for and why it is printed above the figure rather
than in a footnote.

> **What this number is:** a floor on human time, produced by the most advantaged possible
> responder.
> **What it is not:** an estimate of how long a responder who did not know the answer would take.

A floor is still worth having. If the pipeline is *slower* than someone who already knew the
answer, that is a real and damning comparison. If it is faster, the correct reading is "faster
than a fully-informed expert", which is a weaker claim than it looks and is the one the rendering
makes.

## Why this is deliberately not a `variance.Figure`

Every other quantity here is a `Figure` and cannot be built without mean, CI, n and R - the rule
that stops unsourced numbers reaching a report. **Applying it here would do the opposite of its
purpose.**

A `Figure` around five self-timed observations from a single contaminated rater would manufacture
exactly the appearance of rigour the plan warns about: a confidence interval implies a sampling
model, and there is none here. So `Reference` renders as a range and a median with the sample size
and the contamination attached, in a shape that **cannot be mistaken for** the pipeline's figures,
and `render()` refuses to emit a CI at all.

That is the plan's sentence taken literally: *an unsourced number next to a rigorously sourced one
damages the rigorous one* - and the damage is done by making them look alike.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER = REPO_ROOT / "evals/manual-rca/attempts.jsonl"
"""Append-only, like the calibration ledger and for the same reason: an attempt that can be edited
in place is an attempt whose history is unrecoverable, and a slow one that gets quietly rerun is
exactly what makes a self-timed number worthless."""

TARGET_SCENARIOS = 5
"""T4.7's *"five dev scenarios"*. Reported against rather than enforced - a partial reference is a
real result, and refusing to print one below the target hides the state the project is in."""

LABEL = "n=5, self-timed, indicative"
"""The plan's own words, used verbatim as the label.

Mechanical rather than remembered, for the reason `smoke.NON_CITABLE` is: a convention that lives
in a reviewer's memory survives until the first person who was not in the conversation.
"""

CONTAMINATION = (
    "THE RESPONDER AUTHORED THESE SCENARIOS. She wrote every fault, injection and recorded "
    "narrative in this catalog, so these timings measure how long it takes someone who already "
    "knows the answer to confirm it - not how long a responder would take to find it. This is a "
    "FLOOR on human time, produced by the most advantaged possible responder, and a pipeline "
    "that beats it has beaten a fully-informed expert rather than a working one."
)
"""Printed **above** the number, never in a footnote.

There is no fix available inside this project: a second responder is not available, a holdout
scenario does not help because she authored those too, and waiting for forgetting is not a method.
So the contamination is disclosed rather than mitigated, and disclosed where it cannot be skipped.
"""


class AttemptError(ValueError):
    """An attempt that cannot be recorded as stated."""


@dataclass(frozen=True, slots=True)
class Attempt:
    """One self-timed manual investigation."""

    scenario_id: str
    started_at: str
    finished_at: str
    elapsed_seconds: float
    fault_class: str
    service: str
    notes: str = ""
    gave_up: bool = False
    """**A recorded outcome, not a missing one.** An investigation abandoned after twenty minutes
    is data about difficulty; dropping it would make the median a median over the easy ones."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": self.elapsed_seconds,
            "fault_class": self.fault_class,
            "service": self.service,
            "notes": self.notes,
            "gave_up": self.gave_up,
        }


def record(attempt: Attempt, ledger: Path = LEDGER) -> Attempt:
    if attempt.elapsed_seconds <= 0:
        raise AttemptError("an attempt with no elapsed time was not timed")
    if not attempt.gave_up and not attempt.fault_class:
        raise AttemptError(
            "an attempt that reached a conclusion must say what it concluded. If it reached none, "
            "record it with gave_up - an abandoned investigation is data about difficulty, and "
            "dropping it would make the median a median over the easy ones."
        )
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a") as handle:
        handle.write(json.dumps(attempt.as_dict(), sort_keys=True) + "\n")
    return attempt


def load(ledger: Path = LEDGER) -> list[Attempt]:
    if not ledger.exists():
        return []
    return [Attempt(**json.loads(line)) for line in ledger.read_text().splitlines() if line.strip()]


def median(values: list[float]) -> float | None:
    """Median rather than mean. **One long investigation should not move the reference**, and with
    five observations a mean is one bad afternoon away from being a different number."""
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


@dataclass(frozen=True, slots=True)
class Reference:
    """The manual-RCA reference. **Deliberately not a `variance.Figure`** - see the docstring."""

    attempts: tuple[Attempt, ...] = field(default_factory=tuple)

    @property
    def completed(self) -> tuple[Attempt, ...]:
        return tuple(a for a in self.attempts if not a.gave_up)

    @property
    def correct(self) -> tuple[Attempt, ...]:
        """Attempts whose fault class matched the scenario's label.

        Reported because a fast wrong answer is not a reference for anything - but **not used to
        filter the timings**, since excluding the wrong ones would time only the investigations
        that went well.
        """
        from evalharness.run import bundle_for

        matched = []
        for attempt in self.completed:
            try:
                truth = bundle_for(attempt.scenario_id).get("fault_class")
            except Exception:  # a missing bundle is not a scoring failure here
                continue
            if truth and attempt.fault_class == truth:
                matched.append(attempt)
        return tuple(matched)

    @property
    def median_seconds(self) -> float | None:
        """Over every attempt that reached a conclusion, right or wrong."""
        return median([a.elapsed_seconds for a in self.completed])

    @property
    def spread(self) -> tuple[float, float] | None:
        if not self.completed:
            return None
        times = [a.elapsed_seconds for a in self.completed]
        return (min(times), max(times))

    def render(self) -> list[str]:
        """The reference, in a shape that cannot be mistaken for a pipeline figure.

        **No confidence interval, deliberately.** A CI implies a sampling model and there is none
        here; emitting one would manufacture the appearance of rigour the plan warns about, which
        is the mechanism by which an unsourced number damages a sourced one.
        """
        if not self.attempts:
            return [
                "### Manual RCA reference",
                "",
                "*Not yet measured.* The MTTR claim has no left-hand side until it is: "
                '"three minutes to a report" is a number with no denominator.',
                "",
            ]
        lines = [
            "### Manual RCA reference",
            "",
            f"> **{CONTAMINATION}**",
            "",
            f"**{LABEL}** — {len(self.attempts)} attempt(s) of {TARGET_SCENARIOS}, "
            f"{len(self.completed)} reaching a conclusion, {len(self.correct)} of those correct.",
            "",
        ]
        spread, mid = self.spread, self.median_seconds
        if mid is not None and spread is not None:
            lines += [
                f"Median **{mid / 60:.1f} min**, range {spread[0] / 60:.1f} to "
                f"{spread[1] / 60:.1f} "
                f"min over {len(self.completed)} attempt(s).",
                "",
                "**No confidence interval is given and none should be inferred.** Five self-timed "
                "observations from a single rater have no sampling model, and a CI here would "
                "manufacture the appearance of rigour that the rest of this report earns "
                "properly. This number is a reference point, not a measurement.",
                "",
            ]
        else:
            lines += ["No attempt reached a conclusion, so there is no median.", ""]
        gave_up = [a for a in self.attempts if a.gave_up]
        if gave_up:
            lines += [
                f"**{len(gave_up)} attempt(s) abandoned**: "
                f"{', '.join(sorted(a.scenario_id for a in gave_up))}. Recorded rather than "
                "dropped - an abandoned investigation is data about difficulty, and excluding it "
                "would make the median a median over the easy ones.",
                "",
            ]
        return lines
