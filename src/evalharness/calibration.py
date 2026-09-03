"""Judge calibration: grading the judge, blind (T4.2).

T4.2's credibility clause: *"judge calibration (agreement rate with your spot-audits) is what
makes it credible in an interview"*, from *"~30 manually graded runs establish the agreement
baseline **before trusting it**"*.

Every accuracy figure this repository publishes about root-cause agreement is a model's opinion of
another model's prose. That is a defensible instrument **only if somebody has checked it against a
human on the same runs**, and this module is the checking.

## Blind, and that is the whole design

**The grader records a verdict before seeing the judge's.** `next_ungraded()` returns a run's
narrative and the recorded reference and nothing else; the judge's answer is revealed only by
`reveal()`, after a grade exists on disk.

A harness that showed both at once would not measure agreement. It would measure how often a
person confirms a machine, which is a different and much higher number, and the difference is
invisible in the output - both produce a percentage that looks like calibration. This is the one
property of this module that cannot be added later, because the runs already graded unblinded
would have to be discarded.

Two smaller consequences of the same principle:

- **The order is shuffled from a fixed seed.** Run directories sort chronologically, so grading in
  order means grading pipeline generations in order, and a grader who notices they are working
  forwards through the project's history is being told something about each run before reading it.
- **A grade is never revised after the reveal.** The same rule as *no re-runs to improve a number*
  (ADR-0022 §3.3). `regrade` exists and writes a second record rather than overwriting, so a
  changed mind is visible as one.

## Raw agreement is the wrong headline, and the record shows why

T4.2 asks for an *"agreement rate"*, and the naive one is misleading here in a way worth stating
before any grading happens.

The judged record is **15 `same_mechanism`, 3 `adjacent`, 1 `different`** across 19 runs
(`docs/RESULTS.md`). A grader who answered `same_mechanism` every single time - contributing
nothing at all - would score **79% raw agreement**. A headline of "79% agreement with human
audit" would be a number produced by a constant function.

So `Agreement` reports raw agreement **and Cohen's κ**, which subtracts the agreement expected by
chance given each rater's own distribution. Both are printed; κ is the one that answers the
question T4.2 is asking. `interpretation()` states the band in words, because a κ reported without
one invites a reader to assume any positive number is good.

## What this cannot do

It cannot tell you the judge is *right* - only that a human reading the same two documents reaches
the same verdict at some rate. Judge and grader can agree and both be wrong, and on a benchmark
whose ground truth is a narrative written by that same human, they share a prior by construction.
Stated because the figure will be quoted, and it is the caveat most likely to be dropped.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER = REPO_ROOT / "evals/calibration/grades.jsonl"
"""Append-only. One JSON object per grade, in the order they were made.

**Append-only rather than a table**, for ADR-0022 §3.3's reason: a grade that can be edited in
place is a grade whose history is unrecoverable, and the interesting case - a grader changing
their mind after seeing the judge - is exactly the one an overwrite would erase.
"""

LEVELS = ("same_mechanism", "adjacent", "different")
"""ADR-0022 §1.3's three, and the grader uses the judge's own scale.

A scale of the grader's own would make disagreement uninterpretable: two raters using different
vocabularies disagree about the vocabulary, not about the run.
"""

SHUFFLE_SEED = 4_2026
"""Fixed, so the grading order is reproducible and reviewable.

Reproducible matters more than random here: a reader should be able to confirm that the order was
not chosen after the grades were seen. See the module docstring on why chronological order is
worse than useless.
"""

TARGET_GRADES = 30
"""T4.2's *"~30 manually graded runs"*. Reported against, never enforced - a partial calibration
is a real result and refusing to print one below the target would hide the state the project is
actually in."""


@dataclass(frozen=True, slots=True)
class Grade:
    """One human verdict on one run. **Recorded before the judge's is shown.**"""

    run_id: str
    scenario_id: str
    agreement: str
    reason: str
    graded_at: str
    grader: str = ""
    blind: bool = True
    """False only on a `regrade`, which is written as a second record. A figure computed over
    unblinded grades is not a calibration and `Agreement` refuses to mix them."""

    supersedes: str | None = None
    """The `graded_at` of the grade this revises. Set by `regrade`; the original stays."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "agreement": self.agreement,
            "reason": self.reason,
            "graded_at": self.graded_at,
            "grader": self.grader,
            "blind": self.blind,
            "supersedes": self.supersedes,
        }


class InvalidGradeError(ValueError):
    """A grade outside `LEVELS`, or with no reason.

    A reason is required for the same purpose `Candidate.why_not` is: a verdict with no stated
    basis cannot be argued with, and the point of a human audit is that it can be.
    """


def record(grade: Grade, ledger: Path = LEDGER) -> Grade:
    if grade.agreement not in LEVELS:
        raise InvalidGradeError(f"{grade.agreement!r} is not one of {LEVELS}")
    if not grade.reason.strip():
        raise InvalidGradeError(
            "a grade needs a reason. A verdict with no stated basis cannot be argued with, and "
            "the point of a human audit is that it can be."
        )
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a") as handle:
        handle.write(json.dumps(grade.as_dict(), sort_keys=True) + "\n")
    return grade


def load(ledger: Path = LEDGER) -> list[Grade]:
    if not ledger.exists():
        return []
    grades: list[Grade] = []
    for line in ledger.read_text().splitlines():
        if line.strip():
            grades.append(Grade(**json.loads(line)))
    return grades


def current(grades: list[Grade]) -> dict[str, Grade]:
    """The standing grade per run: the last one recorded. **Superseded grades stay in the file.**"""
    standing: dict[str, Grade] = {}
    for grade in grades:
        standing[grade.run_id] = grade
    return standing


def order(run_ids: list[str], seed: int = SHUFFLE_SEED) -> list[str]:
    """Grading order: shuffled from a fixed seed, never chronological.

    Run directories sort by time, so chronological order is generation order - and a grader who
    can tell they are working forwards through the project's history has been told something
    about each run before reading it. Fixed seed so the order is reproducible, and a reader can
    confirm it was not chosen after the grades were seen.
    """
    shuffled = list(run_ids)
    random.Random(seed).shuffle(shuffled)
    return shuffled


def next_ungraded(run_ids: list[str], grades: list[Grade]) -> str | None:
    graded = set(current(grades))
    for run_id in order(run_ids):
        if run_id not in graded:
            return run_id
    return None


@dataclass(frozen=True, slots=True)
class Agreement:
    """Raw agreement and Cohen's κ over the runs both rated."""

    pairs: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    """`(judge, grader)` per run, in `LEVELS` vocabulary."""

    unblinded: int = 0
    """Grades excluded because they were not blind. **Excluded, not counted** - a grade made after
    seeing the judge's answer measures confirmation, not agreement."""

    @property
    def n(self) -> int:
        return len(self.pairs)

    @property
    def raw(self) -> float | None:
        """Proportion of runs the two rated identically.

        **Not the headline.** See the module docstring: with 15 of 19 judged `same_mechanism`, a
        grader who always answered `same_mechanism` scores 79% here while contributing nothing.
        """
        if not self.pairs:
            return None
        return sum(1 for a, b in self.pairs if a == b) / self.n

    @property
    def expected(self) -> float | None:
        """Agreement expected by chance, from each rater's own marginal distribution."""
        if not self.pairs:
            return None
        judge = [a for a, _ in self.pairs]
        grader = [b for _, b in self.pairs]
        return sum(
            (judge.count(level) / self.n) * (grader.count(level) / self.n) for level in LEVELS
        )

    @property
    def kappa(self) -> float | None:
        """Cohen's κ. **The figure that answers T4.2's question.**

        `None` when chance agreement is 1.0 - both raters used exactly one category, where κ is
        undefined rather than perfect. Returning 1.0 there would report a constant function as a
        calibrated instrument, which is the specific failure this module was written to avoid.
        """
        raw, expected = self.raw, self.expected
        if raw is None or expected is None or expected >= 1.0:
            return None
        return (raw - expected) / (1 - expected)

    def interpretation(self) -> str:
        """The band, in words. A κ printed without one invites a reader to assume any positive
        number is good."""
        kappa = self.kappa
        if kappa is None:
            return (
                "undefined - both raters used a single category, so there is no agreement beyond "
                "chance to measure. This is not a perfect score; it is an absent one."
            )
        if kappa < 0:
            return "worse than chance - the two raters disagree systematically"
        if kappa < 0.20:
            return "slight - the judge is not established as a substitute for a reader"
        if kappa < 0.40:
            return "fair - below what a published figure should rest on"
        if kappa < 0.60:
            return "moderate"
        if kappa < 0.80:
            return "substantial"
        return "almost perfect"

    def render(self) -> list[str]:
        raw, kappa = self.raw, self.kappa
        lines = [
            "### Judge calibration",
            "",
            f"**{self.n} of ~{TARGET_GRADES} runs graded blind.**"
            + (
                f" {self.unblinded} regrade(s) excluded: a grade made after seeing the judge's "
                "answer measures confirmation, not agreement."
                if self.unblinded
                else ""
            ),
            "",
        ]
        if raw is None:
            return [*lines, "*No blind grades recorded yet.*", ""]
        lines += [
            f"| raw agreement | {raw:.0%} |",
            "|---|---|",
            f"| Cohen's κ | {'—' if kappa is None else f'{kappa:.2f}'} |",
            f"| reading | {self.interpretation()} |",
            "",
            "**κ is the figure, not raw agreement.** The judged record is heavily skewed toward "
            "`same_mechanism`, so a grader who answered it every time would post a high raw "
            "number while contributing nothing. κ subtracts the agreement expected by chance "
            "from each rater's own distribution.",
            "",
            "Neither figure says the judge is **right**. It says a human reading the same two "
            "documents reached the same verdict at some rate - and on a benchmark whose "
            "reference narrative that same human wrote, judge and grader share a prior by "
            "construction.",
            "",
        ]
        return lines


def agreement(judged: dict[str, str], grades: list[Grade]) -> Agreement:
    """Compare the judge's verdicts to the standing human grades.

    `judged` maps `run_id` to the judge's `agreement` level. Only runs present in both, and only
    **blind** grades, enter the figure.
    """
    standing = current(grades)
    pairs: list[tuple[str, str]] = []
    unblinded = 0
    for run_id, grade in standing.items():
        if run_id not in judged:
            continue
        if not grade.blind:
            unblinded += 1
            continue
        pairs.append((judged[run_id], grade.agreement))
    return Agreement(pairs=tuple(pairs), unblinded=unblinded)


def regrade(original: Grade, agreement_level: str, reason: str) -> Grade:
    """A revised grade, written as a **second record** rather than an overwrite.

    A changed mind after the reveal is informative - it may say the rubric is ambiguous - and
    erasing it would make the ledger claim a confidence the grading did not have. `blind` is
    False, so `agreement()` excludes it from the figure while the file keeps it.
    """
    return Grade(
        run_id=original.run_id,
        scenario_id=original.scenario_id,
        agreement=agreement_level,
        reason=reason,
        graded_at=datetime.now(UTC).isoformat(),
        grader=original.grader,
        blind=False,
        supersedes=original.graded_at,
    )
