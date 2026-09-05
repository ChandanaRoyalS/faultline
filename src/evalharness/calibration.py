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
from collections import Counter
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

UNCALIBRATED = (
    "JUDGE NOT CALIBRATED - {n} of ~{target} blind human grades on file. Every root-cause "
    "agreement figure below is one model's opinion of another model's prose, and no human has "
    "checked it at the sample size T4.2 asks for. Treat these as provisional: a figure that "
    "turns out to disagree with a human audit is withdrawn, not footnoted."
)
"""Printed wherever a judge-derived figure is produced, until the ledger reaches its target.

**The same mechanism as `smoke.NON_CITABLE`, for the same stated reason**: *"so a smoke number
can't be screenshotted into a README six weeks later"*. A convention that lives in a reviewer's
memory survives until the first person who was not in the conversation.

T4.2's clause is *"~30 manually graded runs establish the agreement baseline **before trusting
it**"*. The "before" is the load-bearing word: figures published while this label stands are
resting on an unvalidated instrument, and if the calibration later comes back weak they get
withdrawn rather than annotated. The label disappears on its own when the grades exist - nobody
has to remember to remove it.
"""

CALIBRATED = "Judge calibrated against {n} blind human grades over {scenarios} scenario(s)."

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


def stratified(runs: dict[str, tuple[str, str]], seed: int = SHUFFLE_SEED) -> list[str]:
    """Grading order that covers the record instead of sampling it.

    `runs` maps run id to `(scenario_id, judge_level)`.

    **Uniform random order was the wrong default here, and the pool is why.** Measured on the
    committed record: 61 gradable runs spanning **13 distinct scenarios**, one of them 14 times,
    and the judge said `same_mechanism` on 57 of the 61. Two consequences, and the second is the
    one that decides the design:

    **The rows are not independent.** A grader who has read one scenario's recorded narrative is
    not a blind reader of it the next thirteen times - they already hold a verdict, and their
    later grades on that scenario are correlated with their first by construction. Thirty rows
    drawn uniformly would be perhaps eight distinct cases, counted as thirty.

    **κ is a lottery on four rows.** Only four runs in the pool carry a judge verdict other than
    `same_mechanism`. On 28 `same_mechanism` and 2 `adjacent`, one grader disagreement gives
    κ = 0.65 and two give **κ = 0.00 at 93% raw agreement** - so the headline would be decided by
    which of those four a shuffle happened to deal.

    So the order is built to cover: **every scenario once before any scenario twice**, and every
    non-modal judge verdict inside the first pass. Within that, shuffled from the same fixed seed.

    **The grader is told none of this, and that is a requirement rather than an omission.** A row
    the grader knows was selected for being interesting has been pre-judged for them - a subtler
    unblinding than seeing the judge's answer, and harder to notice afterwards. `--next` prints
    the same two documents for a stratified row as for any other.
    """
    modal = Counter(level for _, level in runs.values()).most_common(1)
    common = modal[0][0] if modal else ""

    remaining = set(order(sorted(runs), seed))
    passes: list[str] = []
    while remaining:
        seen: set[str] = set()
        this_pass: list[str] = []
        for run_id in order(sorted(remaining), seed):
            scenario, _ = runs[run_id]
            if scenario not in seen:
                seen.add(scenario)
                this_pass.append(run_id)
        # Every non-modal verdict joins the first pass, wherever its scenario already sits: they
        # are the only rows where agreement is informative about the *scale* rather than about
        # the base rate, and a first pass without them measures the base rate alone.
        if not passes:
            this_pass += [
                run_id
                for run_id in order(sorted(remaining), seed)
                if runs[run_id][1] != common and run_id not in this_pass
            ]
        passes += order(this_pass, seed)
        remaining -= set(this_pass)
    return passes


def next_ungraded(
    run_ids: list[str],
    grades: list[Grade],
    runs: dict[str, tuple[str, str]] | None = None,
) -> str | None:
    """The next run to grade. Stratified when the caller can say what each run is."""
    graded = set(current(grades))
    sequence = stratified(runs, SHUFFLE_SEED) if runs else order(run_ids)
    for run_id in sequence:
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

    abstentions: int = 0
    """Runs excluded from the pool because the pipeline **abstained** (`fault_class: unknown`).

    **The judge grades every abstention `different` by construction**, so there is no judgement to
    agree with: matching it is a free agreement point and differing is a free disagreement, and
    either way the row is noise. `docs/RESULTS.md` already excludes abstentions from its own
    agreement figure for this reason; this harness served them for a day because it did not know.

    Counted rather than silently dropped - 17 of the 78 runs on disk are abstentions, and a pool
    that shrank by 22% without saying so is the same defect one level up."""

    scenarios: int = 0
    """Distinct scenarios among the graded runs. **The number that says what n is worth.**

    61 gradable runs span 13 scenarios, one of them 14 times. A grader who has read a scenario's
    recorded narrative is not a blind reader of it again, so repeats are correlated by
    construction and `n` overstates the information. Printed beside `n` so no reader takes 30
    rows for 30 independent judgements."""

    @property
    def n(self) -> int:
        return len(self.pairs)

    @property
    def raw(self) -> float | None:
        """Proportion of runs the two rated identically. **The headline, with its own caveat.**

        This module was written believing κ should lead and raw agreement was the misleading one.
        Half of that is right: a grader who answered `same_mechanism` every time would post ~93%
        here while contributing nothing, so raw agreement alone flatters.

        **But κ on this pool is worse, not better.** Measured on 28 `same_mechanism` and 2
        `adjacent`, one grader disagreement yields κ = 0.65 and two yield **κ = 0.00 at 93% raw
        agreement** - the same grader, one extra row, "substantial" to "no better than chance".
        With four non-modal rows in the whole record, κ is decided by which of them got graded.

        So both print, raw leads, and κ carries `kappa_is_unstable`. A number that swings on one
        row is not made trustworthy by being the theoretically correct one.
        """
        if not self.pairs:
            return None
        return sum(1 for a, b in self.pairs if a == b) / self.n

    @property
    def confusion(self) -> dict[tuple[str, str], int]:
        """Every (judge, grader) cell with a count. **What a single figure cannot show.**

        The interesting question is not "how often did they agree" but *where they parted* - a
        grader who reads `adjacent` as `same_mechanism` and one who reads it as `different` post
        the same agreement rate and disagree about opposite things.
        """
        cells: dict[tuple[str, str], int] = {}
        for pair in self.pairs:
            cells[pair] = cells.get(pair, 0) + 1
        return cells

    @property
    def kappa_is_unstable(self) -> bool:
        """Whether one row could move κ across an interpretation band.

        True when the judge's verdicts are concentrated: fewer than five rows outside its modal
        category is the condition measured on this record, where κ swings from 0.65 to 0.00 on a
        single grader disagreement.
        """
        if not self.pairs:
            return False
        judge = [a for a, _ in self.pairs]
        modal = max(LEVELS, key=judge.count)
        return sum(1 for level in judge if level != modal) < 5

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
            "| | |",
            "|---|---|",
            f"| raw agreement | **{raw:.0%}** |",
            # The flag rides on κ only when there **is** a κ. An undefined κ is not an unstable
            # one, and "— — **unstable**" was what the first draft printed: two em-dashes and a
            # warning about a number that does not exist.
            f"| Cohen's κ | {'—' if kappa is None else f'{kappa:.2f}'}"
            + (
                " **— unstable on this pool, see below**"
                if kappa is not None and self.kappa_is_unstable
                else ""
            )
            + " |",
            f"| reading | {self.interpretation()} |",
            f"| distinct scenarios | {self.scenarios or '—'} |",
            "",
            "**Where they parted**, which no single figure shows — a grader who reads `adjacent` "
            "as `same_mechanism` and one who reads it as `different` post the same agreement rate "
            "and disagree about opposite things:",
            "",
            "| judge | grader | n |",
            "|---|---|---|",
        ]
        lines += [
            f"| `{judge}` | `{grader}`{' ✓' if judge == grader else ''} | {n} |"
            for (judge, grader), n in sorted(self.confusion.items(), key=lambda kv: -kv[1])
        ]
        lines += [""]

        if self.kappa_is_unstable:
            lines += [
                "**κ is reported and should not be the headline on this pool.** Fewer than five "
                "graded runs carry a judge verdict outside its modal category, and κ's chance "
                "term is dominated by that skew: measured on 28 `same_mechanism` and 2 "
                "`adjacent`, **one** grader disagreement gives κ = 0.65 and **two** give κ = 0.00 "
                "at 93% raw agreement. Same grader, one extra row, "
                "*substantial* to *no better than chance*. A figure that swings on one row is not "
                "made trustworthy by being the theoretically correct one.",
                "",
            ]
        if self.scenarios:
            lines += [
                f"**{self.n} grade{'' if self.n == 1 else 's'} over {self.scenarios} distinct "
                f"scenario{'' if self.scenarios == 1 else 's'}.** Repeats of one "
                "scenario are **not independent judgements**: a grader who has read a scenario's "
                "recorded narrative already holds a verdict on it, so `n` overstates how much was "
                "actually rated. The grading order covers every scenario before repeating any.",
                "",
            ]
        if self.abstentions:
            lines += [
                f"**{self.abstentions} abstention(s) excluded from the pool.** A run that returned "
                "`fault_class: unknown` made no claim, and the judge grades every abstention "
                "`different` **by construction** — so matching it is a free agreement point and "
                "differing is a free disagreement. `docs/RESULTS.md` excludes them from its own "
                "agreement figure for the same reason.",
                "",
            ]
        lines += [
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


def standing(ledger: Path | None = None) -> str:
    """One line saying what human backing the judge's figures currently have.

    **Returned as text so a caller cannot accidentally print the figures without it.** Reads the
    ledger directly rather than taking a count, so no call site can pass a number that is out of
    date with the file.

    **`None` rather than `LEDGER` as the default, and it matters.** A default argument is bound
    once, at import - so `def standing(ledger: Path = LEDGER)` captured the module-level path
    forever, and nothing could redirect it afterwards. `judged_rows` calls this with no argument,
    so its label was wired to the repository's real `grades.jsonl` with no seam, and the test
    covering that label read the live file: it asserted the caveat appears, passed for two weeks
    because the ledger held fewer than thirty grades, and went red on `main` the moment the
    thirtieth landed and the caveat correctly cleared. **A test that was green for a reason it
    did not state.** Resolving the path at call time gives it a seam and makes the docstring's
    first sentence true.
    """
    blind = [g for g in current(load(ledger if ledger is not None else LEDGER)).values() if g.blind]
    if len(blind) >= TARGET_GRADES:
        return CALIBRATED.format(n=len(blind), scenarios=len({g.scenario_id for g in blind}))
    return UNCALIBRATED.format(n=len(blind), target=TARGET_GRADES)


def is_calibrated(ledger: Path | None = None) -> bool:
    """Same reasoning as `standing`: the path is resolved when asked, not when imported."""
    grades = current(load(ledger if ledger is not None else LEDGER)).values()
    return len([g for g in grades if g.blind]) >= TARGET_GRADES
