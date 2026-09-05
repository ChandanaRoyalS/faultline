"""The blind draw for T4.7's manual-RCA reference.

`manual_rca` states the contamination this deliverable cannot escape: **the only responder
available authored every scenario.** She wrote the faults, the injections and the recorded
narratives, so timing her cannot measure how long a responder takes to *find* an answer.

That much is fixed. What is not fixed is whether she knows **which** fault is live when the clock
starts, and the difference between those two is the whole of what this module buys:

| | what the timing measures |
|---|---|
| unblinded | how long it takes to *confirm* a known answer |
| **blind within a pool** | how long it takes to *recognise* one of a known set |

Neither is what a working responder faces. The second is strictly closer to it, costs nothing,
and is the only reduction in contamination available inside this project - a second person is not
available, a holdout scenario does not help because she authored those too, and waiting for
forgetting is not a method.

## The seal

The drawn scenario is written to a file whose name says not to open it, and **the recorded
attempt takes its `scenario_id` from that file rather than from the operator.** That is the
design's one load-bearing detail. A flow that asked her to name the scenario when recording her
answer would require her to know it, which would undo the draw at the last step - the same shape
as `faultline-calibrate` revealing the judge's verdict only after the grade is on disk.

**The seal is not security.** It is a `cat` away and it is meant to be: this is a discipline for
someone trying to measure herself honestly, not a control against an adversary. It is written
down so that the transcript shows what was and was not known at each point, which is the property
that makes a self-timed number worth anything at all.

## What this module does not do

**It does not score.** The attempt records what she answered; whether that matched the truth is
`Reference.correct`'s job, computed later against the bundle. Scoring at record time would print
right-or-wrong the moment she answered, and the next draw would be taken by someone who had just
been told how the last one went.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SEAL = REPO_ROOT / "evals/manual-rca/DO-NOT-OPEN-until-answered.json"
"""Where the draw is sealed. **The filename is the instruction**, because a file called
`current.json` is one nobody thinks twice about opening."""

SETTLE_AFTER_ALERT_SECONDS = 90
"""The same wait `evalharness.run` takes before investigating, and for the same reason: the first
alert opens the incident and the rest of the blast radius arrives over the following minute or
two. **Taken before the clock starts**, so the responder is handed the same incident the pipeline
was handed - a responder timed from the first episode would be timed partly on waiting."""


class DrawError(RuntimeError):
    """The draw cannot be made as asked."""


@dataclass(frozen=True, slots=True)
class Draw:
    """One sealed selection: what was picked, when, and out of what."""

    scenario_id: str
    pool: tuple[str, ...]
    drawn_at: str
    incident_id: str = ""
    clock_started_at: str = ""
    """When the responder was handed the incident. **Held in the seal and nowhere else.**

    `manual_rca_cli`'s clock lives in `in-progress.json` with the scenario id inside it, which is
    exactly right for the unblinded flow and would leak the draw in this one - an operator
    checking whether her clock is running would be told what she is looking for. One file, marked
    once, holding both.
    """

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "pool": list(self.pool),
            "drawn_at": self.drawn_at,
            "incident_id": self.incident_id,
            "clock_started_at": self.clock_started_at,
        }

    @property
    def prior(self) -> str:
        """`1 in 5`. **Recorded with the attempt**, because the contamination the reader needs to
        judge is the size of the answer set, and it changes as the pool is used up."""
        return f"1 in {len(self.pool)}"


def remaining(pool: list[str], attempted: list[str]) -> list[str]:
    """The pool minus what has already been drawn. **Without replacement, deliberately.**

    Five attempts over five scenarios is what T4.7 asks for. Drawing with replacement could time
    one scenario three times and leave two unmeasured, and a median over that is a median over one
    scenario's difficulty wearing the label of five.
    """
    taken = set(attempted)
    return [scenario_id for scenario_id in pool if scenario_id not in taken]


def draw(pool: list[str], attempted: list[str], rng: random.Random | None = None) -> str:
    """Pick uniformly from what is left. Refuses an exhausted pool rather than repeating."""
    left = remaining(pool, attempted)
    if not left:
        raise DrawError(
            f"every scenario in the pool of {len(pool)} has been attempted. "
            "Drawing again would time one twice and leave the reference resting on repeats."
        )
    return (rng or random.SystemRandom()).choice(sorted(left))


def seal(drawn: Draw, path: Path = SEAL) -> Path:
    """Write the draw where the operator is asked not to read it.

    Refuses to overwrite an existing seal: two draws open at once means neither timing describes
    one investigation, and the same argument the manual-RCA clock makes about two clocks.
    """
    if path.exists():
        held = json.loads(path.read_text())
        raise DrawError(
            f"a draw is already sealed, made at {held['drawn_at']}. Answer or give up on it "
            "first - two sealed draws means neither attempt has one fault in it."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(drawn.as_dict(), indent=2, sort_keys=True) + "\n")
    return path


def unseal(path: Path = SEAL) -> Draw:
    """Read the seal and remove it. **Called only after the answer is recorded.**"""
    if not path.exists():
        raise DrawError("no draw is sealed; there is nothing being timed")
    held = json.loads(path.read_text())
    return Draw(
        scenario_id=held["scenario_id"],
        pool=tuple(held["pool"]),
        drawn_at=held["drawn_at"],
        incident_id=held.get("incident_id", ""),
        clock_started_at=held.get("clock_started_at", ""),
    )


def sealed(path: Path = SEAL) -> bool:
    return path.exists()


def now() -> str:
    return datetime.now(UTC).isoformat()
