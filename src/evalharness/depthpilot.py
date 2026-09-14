"""Q53's pilot: does retrieval depth change a verdict? (`PREREGISTRATION-Q53.md`, ADR-0041)

Four retrieval write-ups have measured whether a relevant document is **reachable**. None has
measured whether the model reads it and answers differently. This is the driver for the ten-pair
pilot that asks.

**Paired on the incident.** One injection, one incident, **two investigations** - one at
`(normalisation 0, k=3)`, production today, and one at `(normalisation 2, k=5)`, the joint change.
The pair shares a world state, an alert set and a change log, so the only difference between the
two verdicts is what retrieval handed the model. World variance is the dominant noise source in
this benchmark and pairing removes it; ten pairs this way are worth far more than twenty unpaired
runs.

**The second arm is reached through a rejection, and that is forced** (Amendment 1). `ALLOWED`
admits `PLANNING` from `TRIAGING` and from `REJECTED` and from nowhere else, which is why
`INVESTIGABLE` has exactly two members; an incident that has been investigated once is past
`TRIAGING` permanently. There is **no door into a second investigation of one incident that does
not pass through `REJECTED`**, so the registration's §3 design cannot run without one. The dry run
found it after the first arm and before the second: *"incident ... is in state proposing; the
machine investigates from rejected, triaging only."*

**So the outcome narrows to `fault_class` alone.** A rejection reaches the *proposer's* brief and
nothing else - `roles.py`'s `Section(name="operator-rejection", ...)`, pinned by
`test_an_operator_rejection_reaches_the_proposer_in_the_user_message_only` - and T6.3 measured a
rejection's effect on the next proposal at **2 of 2 changed, both abstentions**. So
`remediation_class` is contaminated by an effect this repository has already measured at 100%; it
is recorded and it does not decide. `fault_class` comes from the synthesizer, which never sees the
rejection, working off a reused triage and the same episodes, catalog and corpus - `context/seed.py`
is the only writer to the past-incident store, so the second arm's corpus is byte-identical to the
first's. Retrieval is the only injected difference upstream of the verdict.

**It is a kill switch, not a measurement**, and §3.1 of the registration fixes the arithmetic that
makes that honest: at the retrieval upper bound of 18.6% this sees at least one changed verdict 87%
of the time, at 5% it sees one 40% of the time. So it can falsify *this matters a lot* and cannot
establish *this never matters*, and **no result from it is reported as a rate**.

**This module calls no model itself.** It shells `faultline-investigate` exactly as the harness
does, so the two arms are the pipeline rather than a reimplementation of it, and
`test_the_pilot_calls_no_model_itself` holds the import graph - the same guard `retrieval.py` and
the reject-loop driver carry.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

BASELINE_ARM = "k3-flag0"
CHANGE_ARM = "k5-flag2"

ARMS: dict[str, dict[str, int]] = {
    BASELINE_ARM: {"retrieval_k": 3, "text_normalisation": 0},
    CHANGE_ARM: {"retrieval_k": 5, "text_normalisation": 2},
}
"""The two configurations, and **neither half is tested alone.**

`retrieval_k` alone buys two queries of 43; normalisation 2 alone at `k = 3` buys one, inside
ADR-0040 clause 5's band, and Q52 measured that choosing among flags at that depth is *worse* than
not choosing. Together they buy eight. Q53's queue row named `retrieval_k` as the lever and the
registration corrects it.
"""

SCENARIOS: tuple[str, ...] = (
    "ad-memory-squeeze",
    "cart-bad-image-tag",
    "cart-dependency-latency",
    "cart-redis-misconfig",
    "frauddetection-memory-squeeze",
    "payment-telemetry-blackout",
    "product-catalog-flag-failure",
    "redis-cart-dependency-latency",
    "shipping-quote-misconfig",
    "shipping-wrong-image",
)
"""Ten dev scenarios in catalog order. **No selection** - the registration says so, and a pilot
whose scenarios were chosen would be measuring the chooser."""

BUDGET_CEILING_USD = 25.0
"""**A hard stop, not an estimate.** 24 runs at the measured p90 of $0.787 is $18.89; expected
spend is nearer $12 at the $0.597 median. The registration's words: *a budget that is revised
upward mid-task is not a budget.* Reaching this stops the pilot where it stands and reports the
pairs it did not complete."""

REJECTION_REASON = (
    "This incident is part of a paired retrieval measurement and is not being remediated. "
    "No judgement is offered about your previous proposal and none should be inferred: read "
    "the evidence exactly as you would on a first look."
)
"""**Fixed here, before any run, and identical for all ten pairs.**

`record_rejection` requires a reason (`clean_reason` raises on whitespace) and there is no
reasonless route to `REJECTED`, so the pilot has to supply text the proposer will read. T6.3's
reasons were substantive operator reports - *"restarted cartservice and the alerts kept firing"* -
and were meant to move the proposal. This one is meant not to, and says so.

**It does not succeed at that and the pilot does not pretend it does.** The brief wraps any reason
in *"An operator reviewed your previous proposal for this incident and REJECTED it"* and invites an
abstention, and that framing is not removable from here. What this text buys is that the framing is
**the same in every pair and carries no scenario-specific content**, so it cannot vary with the arm.
What it cannot buy is a clean `remediation_class`, which is why Amendment 1 takes that channel out
of the decision rather than arguing the contamination away.

A reason chosen after seeing a second verdict would be prompt-fitting; this is the reject-loop
driver's rule and the constant is here for the same reason its `PAIRS` are."""

RETRIEVAL_BOUND = 0.186
"""8 of 43 golden queries, §3.1's upper bound on how often retrieval could change anything at all.

Used to price what a run of `n` pairs bought: `1 - (1 - 0.186)**n`. At `n = 10` that is the
registration's 87%; at `n = 1` it is 18.6%, which is the number the fifth dry run should have
printed and did not."""

ATTEMPTS_PER_SCENARIO = 2
"""**One re-attempt, and one only** (Amendment 2, registered before the run).

A pair dies whole when either arm fails, and the incident is then `failed`, which ADR-0016's table
makes terminal - so the retry is a fresh injection, not a resumption. The fourth dry run's arm died
on a `DispatchPlan` the schema refused twice, which is the harness's ordinary discard rate arriving
in the worst place for a paired design: **both halves must score, so 16.7% per run is 30.6% per
pair**, and the registration's own prediction 6 was written against the per-run figure.

Fixed at two before any pair had run, so it is a rule about **run failures** and not about results.
A retry decided after seeing how many pairs completed would be a budget that responds to its own
outcome, which is the shape this repository refuses everywhere else."""

REJECT_PATH = "/api/v1/incidents/{incident_id}/reject"
"""The route the second arm depends on, as FastAPI spells it in the schema."""


def reject_route_is_mounted(schema: dict[str, Any]) -> bool:
    """Is the reject route actually served by the process the pilot will talk to?

    **The fifth precondition, and the one most likely to be missed.** `api/app.py` mounts the
    approve and reject routes only when `FAULTLINE_EXECUTOR_TOKEN_KEY` is set, and **starts anyway
    when it is not** - deliberately, because *"a missing button is not an outage"*. From the pilot's
    side that is invisible: the screen serves, the read routes answer, and the rejection returns a
    bare 404 that looks like a missing incident. It would arrive after the first arm had been paid
    for, ten times.

    Read off `GET /openapi.json`, which is the process's own statement about what it serves, rather
    than probed by sending a rejection somewhere. A probe would need an incident to reject.
    """
    return REJECT_PATH in (schema.get("paths") or {})


def arm_order(index: int) -> tuple[str, str]:
    """Which arm runs first for pair `index`. **Alternated, and that is not cosmetic.**

    The second investigation of a pair runs against an incident that already carries a proposal
    from the first, and whether that matters is unknown - T6.3's reject-loop re-investigates and
    found its driver needed the harness's own bounds before it was comparable at all. Alternating
    does not remove an order effect. It stops one being **confounded with the arm**, which is the
    difference between a result with a caveat and a result that means nothing.
    """
    return (BASELINE_ARM, CHANGE_ARM) if index % 2 == 0 else (CHANGE_ARM, BASELINE_ARM)


def env_for(arm: str, base: dict[str, str] | None = None) -> dict[str, str]:
    """The environment one arm's `faultline-investigate` runs under.

    `text_normalisation` became a setting at Q53 for exactly this: a module constant cannot be
    varied across a subprocess. `retrieval_k` travels the same way rather than as a CLI flag, so
    both halves of a configuration are set by one mechanism and a reader does not have to check
    two places to know what ran.
    """
    settings = ARMS[arm]
    out = dict(base if base is not None else os.environ)
    out["FAULTLINE_CONTEXT_RETRIEVAL_K"] = str(settings["retrieval_k"])
    out["FAULTLINE_CONTEXT_TEXT_NORMALISATION"] = str(settings["text_normalisation"])
    return out


def verdict_from_artifact(
    payload: dict[str, Any], arm: str, *, cost_usd: float = 0.0, documents: tuple[str, ...] = ()
) -> Verdict | None:
    """Read one arm's answer out of `<incident>-verdict.json`.

    **The first version of this queried a `proposals` table that does not exist**, and the dry run
    found it after one paid investigation had already completed. The lesson is not that a name was
    wrong: it is that the pipeline already writes a verdict artifact, `faultline-investigate --out`
    produces it, and `evalharness.run` reads exactly this file. A driver that goes around the
    artifact to reconstruct the same answer from tables is a second implementation of the harness,
    which is the thing this module's own docstring says it must not be.

    `fault_class` is here and **not** in `trajectory_proposals`, which carries `remediation_class`
    only - so the table route could never have answered the question in the first place.
    """
    verdict = payload.get("verdict") or {}
    trajectory_id = str(payload.get("trajectory_id") or "")
    fault_class = str(verdict.get("fault_class") or "")
    if not trajectory_id or not fault_class:
        return None
    return Verdict(
        arm=arm,
        trajectory_id=trajectory_id,
        fault_class=fault_class,
        remediation_class=str(verdict.get("remediation_class") or ""),
        cost_usd=cost_usd,
        documents=documents,
    )


@dataclass(frozen=True, slots=True)
class Verdict:
    """One arm's answer, reduced to what the pilot compares."""

    arm: str
    trajectory_id: str
    fault_class: str
    remediation_class: str
    cost_usd: float
    documents: tuple[str, ...] = ()
    """What retrieval returned, so prediction 7 - that the deeper cut reorders rather than extends
    in most pairs - can be adjudicated from the record rather than re-derived."""


@dataclass
class PairResult:
    scenario_id: str
    incident_id: str = ""
    first_arm: str = ""
    verdicts: dict[str, Verdict] = field(default_factory=dict)
    skipped: str = ""
    rejected: bool = False
    """Whether the incident passed through `REJECTED` between the arms. **True on every complete
    pair**, because it is the only route to a second investigation; recorded rather than assumed so
    that a pair which somehow completed without one would be visible in the artifact."""
    attempt: int = 1
    """1, or 2 for the single re-attempt Amendment 2 allows a scenario whose pair died."""
    spend_usd: float = 0.0
    """What this incident has cost, **across every trajectory on it**, read after each arm.

    **The fourth dry run reported `$0.00` for an investigation that was not free.** The planner ran,
    was refused twice on a `skipped_note` the schema forbids, and the incident went to `failed` - so
    there was no verdict, so the old sum over `verdicts` saw nothing, so the ceiling saw nothing. At
    twenty investigations and a discard rate near a sixth, that is a budget with a blind spot in
    exactly the place a budget exists for."""

    @property
    def complete(self) -> bool:
        return len(self.verdicts) == 2

    @property
    def differs(self) -> bool:
        """**The pilot's whole outcome: a changed `fault_class`.**

        Amendment 1 narrowed this from *fault class or remediation class*. The second arm is only
        reachable through a rejection, a rejection reaches the proposer's brief, and T6.3 measured
        that at 2 of 2 changed proposals - so a moved `remediation_class` here would be evidence
        about the rejection, not about retrieval. The synthesizer that produces `fault_class` never
        sees the rejection, so this channel is clean and it is the one that decides.

        Not "is it better": that is the 30-40 pair measurement this pilot exists to decide whether
        to fund. `n = 10` cannot say which direction dominates and the registration forbids
        reporting it as if it could.
        """
        if not self.complete:
            return False
        return self.verdicts[BASELINE_ARM].fault_class != self.verdicts[CHANGE_ARM].fault_class

    @property
    def remediation_differs(self) -> bool:
        """Recorded, and **deliberately not part of `differs`.**

        Kept because the contamination is an argument rather than a measurement: if this moves in
        roughly half the pairs it is the rejection doing what T6.3 saw, and if it never moves that
        is worth knowing too. Either way it does not decide Q53, and a reader who wants it has to
        read it under the sentence that says why.
        """
        if not self.complete:
            return False
        return (
            self.verdicts[BASELINE_ARM].remediation_class
            != self.verdicts[CHANGE_ARM].remediation_class
        )

    @property
    def cost_usd(self) -> float:
        """`spend_usd` when the world could be asked, and the verdicts' sum otherwise.

        The fallback is not a nicety: it is what a `Steps` fake without a priced world reports, and
        keeping it means the budget tests stay about the ceiling rather than about wiring.
        """
        return self.spend_usd or sum(v.cost_usd for v in self.verdicts.values())


@dataclass
class PilotResult:
    pairs: list[PairResult] = field(default_factory=list)
    stopped: str = ""
    """Why the pilot ended early, if it did. **Empty is the only value that means it finished.**"""

    @property
    def cost_usd(self) -> float:
        return sum(p.cost_usd for p in self.pairs)

    @property
    def complete_pairs(self) -> list[PairResult]:
        return [p for p in self.pairs if p.complete]

    @property
    def differing(self) -> list[PairResult]:
        return [p for p in self.complete_pairs if p.differs]

    def render(self) -> str:
        lines = [
            f"pairs attempted : {len(self.pairs)}",
            f"pairs complete  : {len(self.complete_pairs)}",
            f"verdicts differ : {len(self.differing)} of {len(self.complete_pairs)}",
            f"spend           : ${self.cost_usd:.2f} of ${BUDGET_CEILING_USD:.2f}",
        ]
        if self.stopped:
            lines.append(f"STOPPED EARLY   : {self.stopped}")
        for pair in self.pairs:
            tag = f"{pair.scenario_id}#{pair.attempt}" if pair.attempt > 1 else pair.scenario_id
            if pair.skipped:
                spend = f"  (spent ${pair.cost_usd:.2f})" if pair.cost_usd else ""
                lines.append(f"  {tag}: skipped - {pair.skipped}{spend}")
                continue
            mark = "DIFFERS" if pair.differs else "same" if pair.complete else "incomplete"
            detail = ", ".join(
                f"{arm}={v.fault_class}/{v.remediation_class}"
                for arm, v in sorted(pair.verdicts.items())
            )
            tail = "  [remediation also moved]" if pair.remediation_differs else ""
            lines.append(f"  {tag}: {mark}  first={pair.first_arm}  {detail}{tail}")
        lines.append("")
        lines.append(
            "DIFFERS is a changed fault_class only (Amendment 1). The second arm of every pair is "
            "reached through a rejection, which reaches the proposer's brief and which T6.3 "
            "measured at 2 of 2 changed proposals - so remediation_class is shown and does not "
            "decide."
        )
        if self.complete_pairs and not self.differing:
            lines.append("")
            lines.append(self.closure_reading())
        return "\n".join(lines)

    def closure_reading(self) -> str:
        """What 0-of-n actually licenses, **computed from n rather than asserted.**

        The fifth dry run printed *"0 of 1 differ ... this closes Q53 ... at 87% confidence"*. The
        87% is `1 - (1 - 0.186)**10` and belongs to ten pairs; at one pair the same arithmetic gives
        **18.6%**, and the sentence was a false claim in the driver's own report. It would have
        printed identically had the ten-pair run stopped at three.

        §3.2's closure is written for the registered set. Short of it, this says what was actually
        bought, and says that it is not the closure.
        """
        n = len(self.complete_pairs)
        confidence = 1 - (1 - RETRIEVAL_BOUND) ** n
        head = f"0 of {n} differ. At the retrieval upper bound of {RETRIEVAL_BOUND:.1%}, "
        head += f"{n} pair(s) would have found a change {confidence:.0%} of the time."
        if n < len(SCENARIOS):
            return (
                head + f"  NOT the closure: PREREGISTRATION-Q53.md 3.2 is written for "
                f"{len(SCENARIOS)} complete pairs at 87%, and this run has {n}. Q53 stays open."
            )
        return (
            head + "  Per PREREGISTRATION-Q53.md 3.2 this closes Q53: the effect is below the "
            "retrieval upper bound and the larger measurement is not funded."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "stopped": self.stopped,
            "cost_usd": round(self.cost_usd, 4),
            "ceiling_usd": BUDGET_CEILING_USD,
            "arms": ARMS,
            "outcome_channel": "fault_class",
            "rejection_reason": REJECTION_REASON,
            "amendment": (
                "Amendment 1: the second arm is reachable only through REJECTED, so the outcome "
                "is fault_class alone and remediation_class is recorded as contaminated."
            ),
            "pairs": [
                {
                    "scenario_id": p.scenario_id,
                    "incident_id": p.incident_id,
                    "first_arm": p.first_arm,
                    "attempt": p.attempt,
                    "skipped": p.skipped,
                    "spend_usd": round(p.cost_usd, 4),
                    "complete": p.complete,
                    "rejected": p.rejected,
                    "differs": p.differs,
                    "remediation_differs": p.remediation_differs,
                    "verdicts": {
                        arm: {
                            "trajectory_id": v.trajectory_id,
                            "fault_class": v.fault_class,
                            "remediation_class": v.remediation_class,
                            "cost_usd": round(v.cost_usd, 4),
                            "documents": list(v.documents),
                        }
                        for arm, v in sorted(p.verdicts.items())
                    },
                }
                for p in self.pairs
            ],
        }


class Steps(Protocol):
    """The seam the tests substitute at, so the driver's logic is exercised without a world.

    The reject-loop driver has the same shape and for the same reason: T6.3's two defects - a gate
    weaker than the harness's, and a missing model client discovered *after* a fault was injected -
    were both in the driver rather than in what it drove.
    """

    def gate_admits(self) -> tuple[bool, list[str]]: ...

    def inject(self, scenario_id: str) -> str: ...

    def wait_for_incident(self, scenario_id: str, after: datetime) -> str | None: ...

    def investigate(self, incident_id: str, arm: str) -> Verdict | None:
        """One arm's investigation. `None` when it produced no verdict."""
        ...

    def reject(self, incident_id: str, reason: str) -> None:
        """Move the incident to `REJECTED` so the second arm is legal. Raises on a refusal.

        **Through the route**, not by calling `record_rejection`: the reject-loop driver's rule,
        and here it also means the pilot cannot reach `REJECTED` by any path an operator could not.
        """
        ...

    def spend_on(self, incident_id: str) -> float:
        """Everything this incident has cost so far, across **every** trajectory on it.

        **Not the sum of the verdicts' costs**, which is what this used to be and which reports
        `$0.00` for an investigation that burned a triage and two refused planner attempts before
        dying. Amendment 2: the budget is checked against a number that can see a failed arm.
        """
        ...

    def revert(self, scenario_id: str) -> None: ...


SETTLE_SECONDS = 300
"""The orchestrator's settle window, and **the reason a pilot could only ever complete its first
pair.** Every pair leaves a resolved incident, and a firing inside 300s reopens it rather than
opening a new one - so the next pair's alerts would be attributed to the previous scenario and the
gate refuses outright. `sweep.py` learned this first and carries the same constant; this mirrors it
rather than inventing a second number.

**Found by the dry run, before any money was spent on it.** The gate's refusal said *"Wait 141s"*,
which is what made the gap visible: without this the ten-pair run would complete pair one, refuse
pairs two through ten, and report `n = 1` for $1.20."""


def run_pilot(
    steps: Steps,
    scenarios: tuple[str, ...] = SCENARIOS,
    *,
    ceiling_usd: float = BUDGET_CEILING_USD,
    settle: int = 0,
    sleeper: Any = None,
) -> PilotResult:
    """Ten pairs, or as many as the budget allows.

    **The gate is checked before every injection**, not once at the start - T6.3's first defect was
    a driver whose gate was weaker than the harness's, and a leftover incident from an aborted run
    swallowed the next scenario's alerts.

    **The budget is checked before each investigation**, not after. A ceiling enforced after the
    spend is a report, not a limit.

    **The rejection sits between the arms and nowhere else.** It is what makes the second
    investigation legal at all, and it cannot be moved earlier: an incident is only rejectable once
    something has proposed on it (`REJECTABLE` is `PROPOSING`, `SYNTHESIZING`, `AWAITING_APPROVAL`),
    so the first arm has to have run and been paid for before the pilot knows the pair can complete.
    A refusal there loses the pair **and the first arm's spend**, which is recorded in `skipped`
    rather than raised - the alternative is a driver that can die holding an injected fault.

    **The world is reverted in a `finally`**, because a pilot that leaves a fault injected has cost
    more than money.

    **`settle` defaults to 0 and that is deliberate**, on `sweep.py`'s precedent: *"the first
    version defaulted without a sleeper and tried to nap for twenty minutes"*. Waiting is a property
    of running the pilot, not of the function, and a default that sleeps is one nobody can call in a
    test without knowing to disarm it. The CLI passes `SETTLE_SECONDS`.
    """
    import time

    nap = sleeper if sleeper is not None else time.sleep
    result = PilotResult()
    started_one = False
    for index, scenario_id in enumerate(scenarios):
        for attempt in range(1, ATTEMPTS_PER_SCENARIO + 1):
            if started_one and settle:
                print(f"--- settling {settle}s before {scenario_id} #{attempt}", flush=True)
                nap(settle)
            started_one = True

            pair = _attempt_pair(
                steps, scenario_id, index, attempt=attempt, result=result, ceiling_usd=ceiling_usd
            )
            result.pairs.append(pair)
            if result.stopped or pair.complete or attempt == ATTEMPTS_PER_SCENARIO:
                break
        if result.stopped:
            break
    return result


def _attempt_pair(
    steps: Steps,
    scenario_id: str,
    index: int,
    *,
    attempt: int,
    result: PilotResult,
    ceiling_usd: float,
) -> PairResult:
    """One injection and its two arms. **The arm order comes from `index`, never from `attempt`** -
    a re-attempt that flipped the order would confound the retry with the arm, which is the exact
    confound `arm_order` exists to prevent."""
    pair = PairResult(scenario_id=scenario_id, attempt=attempt)

    if result.cost_usd >= ceiling_usd:
        result.stopped = f"budget ceiling ${ceiling_usd:.2f} reached before {scenario_id}"
        pair.skipped = "budget"
        return pair

    admitted, refusals = steps.gate_admits()
    if not admitted:
        pair.skipped = f"gate refused: {'; '.join(refusals)}"
        return pair

    started = datetime.now(UTC)
    steps.inject(scenario_id)
    try:
        incident_id = steps.wait_for_incident(scenario_id, started)
        if not incident_id:
            pair.skipped = "no incident"
            return pair
        pair.incident_id = incident_id

        first, second = arm_order(index)
        pair.first_arm = first
        for position, arm in enumerate((first, second)):
            if result.cost_usd + pair.cost_usd >= ceiling_usd:
                result.stopped = f"budget ceiling ${ceiling_usd:.2f} reached in {scenario_id}"
                break
            if position:
                try:
                    steps.reject(incident_id, REJECTION_REASON)
                except Exception as exc:
                    pair.skipped = f"rejection refused: {type(exc).__name__}: {exc}"
                    break
                pair.rejected = True
            verdict = steps.investigate(incident_id, arm)
            pair.spend_usd = steps.spend_on(incident_id)
            if verdict is None:
                pair.skipped = f"{arm} produced no verdict"
                break
            pair.verdicts[arm] = verdict
    finally:
        steps.revert(scenario_id)
    return pair


class LiveSteps:  # pragma: no cover - the paid path; the fakes cover the logic
    """The real world. Every operation is the harness's own, never a reimplementation.

    `faultline-investigate` is shelled rather than imported, for the reason Q53's registration
    gives: the two arms have to be **the pipeline**, and a driver that constructed an
    `Investigation` itself would be measuring a second implementation that happens to live in the
    same repository. It is also what lets `env_for` vary the configuration at all.
    """

    def __init__(
        self,
        dsn: str | None = None,
        *,
        api_url: str = "http://127.0.0.1:8000",
        api_user: str = "faultline",
        api_password: str = "",
    ) -> None:
        import base64

        from faultline.context.settings import ContextSettings

        self._dsn = dsn or ContextSettings().postgres_dsn
        self._api = api_url.rstrip("/")
        self._auth = base64.b64encode(f"{api_user}:{api_password}".encode()).decode()
        """Built once and never logged. The password arrives in the environment and leaves in a
        header; it is in no file this driver writes. The reject-loop driver's rule, verbatim."""

    def gate_admits(self) -> tuple[bool, list[str]]:
        from evalharness import gate
        from evalharness.run import open_incidents, settling_incidents

        reading = gate.read(
            open_incidents(self._dsn), settling_incidents(self._dsn), runs_remaining=1
        )
        return reading.passed, list(reading.refusals)

    def inject(self, scenario_id: str) -> str:
        from evalharness.run import _sh

        code, out = _sh(["faultline-inject", "start", scenario_id])
        if code != 0:
            raise RuntimeError(f"injection failed:\n{out}")
        return out

    def wait_for_incident(self, scenario_id: str, after: datetime) -> str | None:
        from evalharness.run import RunError, bundle_for, expected_episodes, wait_for_incident

        try:
            return wait_for_incident(self._dsn, after, expected_episodes(bundle_for(scenario_id)))
        except RunError as exc:
            print(f"  {exc}")
            return None

    def investigate(self, incident_id: str, arm: str) -> Verdict | None:
        """One arm, through the CLI, reading the artifact the CLI writes.

        **Each arm gets its own output directory.** Both halves of a pair share an incident, so
        both write `<incident>-verdict.json` - into one directory the second would overwrite the
        first and the pilot would compare an arm against itself.

        Nothing here raises. A driver whose verdict read can end the run is a driver that can leave
        a fault injected on a world nobody is watching, and the whole pilot was stopped once
        already by exactly that.
        """
        import subprocess
        import tempfile

        from faultline.orchestrator.settings import OrchestratorSettings

        with tempfile.TemporaryDirectory(prefix=f"q53-{arm}-") as tmp:
            argv = [
                "faultline-investigate",
                incident_id,
                "--out",
                tmp,
                *OrchestratorSettings().investigate_args,
            ]
            completed = subprocess.run(
                argv, check=False, capture_output=True, text=True, env=env_for(arm)
            )
            print(completed.stdout)
            if completed.returncode != 0:
                print(f"  {arm}: faultline-investigate exited {completed.returncode}")
                print(completed.stderr[-2000:])
                return None
            artifact = Path(tmp) / f"{incident_id}-verdict.json"
            if not artifact.exists():
                print(f"  {arm}: the investigation wrote no verdict artifact")
                return None
            try:
                payload = json.loads(artifact.read_text())
            except (OSError, ValueError) as exc:
                print(f"  {arm}: unreadable verdict artifact: {exc}")
                return None

        trajectory_id = str(payload.get("trajectory_id") or "")
        return verdict_from_artifact(
            payload,
            arm,
            cost_usd=self._cost_of(trajectory_id),
            documents=self._documents_of(trajectory_id),
        )

    def spend_on(self, incident_id: str) -> float:
        """Every token on every trajectory this incident has, priced.

        **Joined through `trajectories.incident_id` rather than summed from the verdicts**, because
        an investigation that dies before a verdict still has a trajectory and still has steps. The
        fourth dry run is the case: triage, then a planner refused twice on a field `DispatchPlan`
        forbids, then `failed` - no verdict, and under the old accounting, no spend.

        Zero on any failure, for `_cost_of`'s reason: a pilot that cannot price a run it has already
        paid for should report the run. That makes the ceiling less conservative on a database
        error, which is a real limitation and is better than an exception mid-pair.
        """
        import psycopg

        from faultline.agents.settings import AgentSettings

        if not incident_id:
            return 0.0
        try:
            with psycopg.connect(self._dsn) as conn:
                row = conn.execute(
                    "SELECT coalesce(sum(s.tokens_in), 0), coalesce(sum(s.tokens_out), 0) "
                    "FROM trajectory_steps s JOIN trajectories t ON s.trajectory_id = t.id "
                    "WHERE t.incident_id = %s",
                    (incident_id,),
                ).fetchone()
        except Exception as exc:  # pragma: no cover - observational
            print(f"  could not price incident {incident_id}: {type(exc).__name__}")
            return 0.0
        if not row:
            return 0.0
        settings = AgentSettings()
        cost = row[0] * settings.usd_per_mtok_in + row[1] * settings.usd_per_mtok_out
        return float(cost) / 1_000_000

    def _cost_of(self, trajectory_id: str) -> float:
        """From the recorded tokens. **Zero on any failure**, because a pilot that cannot price a
        run it already paid for should report the run, not lose it - and the budget ceiling is
        checked against the total, so an unpriced run makes the ceiling *more* conservative in the
        wrong direction. That is a real limitation and it is better than an exception."""
        import psycopg

        from faultline.agents.settings import AgentSettings

        if not trajectory_id:
            return 0.0
        try:
            with psycopg.connect(self._dsn) as conn:
                row = conn.execute(
                    "SELECT coalesce(sum(tokens_in), 0), coalesce(sum(tokens_out), 0) "
                    "FROM trajectory_steps WHERE trajectory_id = %s",
                    (trajectory_id,),
                ).fetchone()
        except Exception as exc:  # pragma: no cover - observational
            print(f"  could not price {trajectory_id}: {type(exc).__name__}")
            return 0.0
        if not row:
            return 0.0
        settings = AgentSettings()
        cost = row[0] * settings.usd_per_mtok_in + row[1] * settings.usd_per_mtok_out
        return float(cost) / 1_000_000

    def _documents_of(self, trajectory_id: str) -> tuple[str, ...]:
        """What retrieval returned, for prediction 7. Empty on any failure - it is evidence for a
        prediction, not a thing the pilot turns on."""
        import psycopg

        if not trajectory_id:
            return ()
        try:
            with psycopg.connect(self._dsn) as conn:
                row = conn.execute(
                    "SELECT returned FROM trajectory_retrievals WHERE trajectory_id = %s "
                    "ORDER BY seq DESC LIMIT 1",
                    (trajectory_id,),
                ).fetchone()
        except Exception:  # pragma: no cover - observational
            return ()
        return tuple(row[0]) if row and row[0] else ()

    def reject(self, incident_id: str, reason: str) -> None:
        """`POST /api/v1/incidents/{id}/reject`, the surface an operator uses.

        **Not `record_rejection`.** Calling the function would let the pilot reach `REJECTED` by a
        path no operator has, and the whole reason the second arm is legal is that an operator
        *could* have put the incident there. The route also enforces the rejection cap and writes
        the ledger row, both of which should exist for these ten incidents like any other.
        """
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            f"{self._api}/api/v1/incidents/{incident_id}/reject",
            data=json.dumps({"reason": reason}).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {self._auth}",
            },
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=30).close()
        except urllib.error.HTTPError as failure:
            raise RuntimeError(
                f"{failure.code}: {failure.read().decode(errors='replace')[:400]}"
            ) from None

    def revert(self, scenario_id: str) -> None:
        from evalharness.run import _sh

        code, out = _sh(["faultline-inject", "stop", scenario_id])
        if code != 0:
            print(f"  WARNING: revert of {scenario_id} exited {code}:\n{out}")


def run_cli(argv: list[str] | None = None) -> int:  # pragma: no cover - the live path
    import argparse

    parser = argparse.ArgumentParser(
        prog="faultline-depth-pilot",
        description=(
            "Q53's ten-pair pilot. Spends money. Read PREREGISTRATION-Q53.md first: this is a "
            "kill switch, not a measurement, and it adopts nothing whatever it finds. "
            "Needs faultline-ingest running with the executor key, because the second arm of "
            "every pair is reached by rejecting the first arm's proposal through the route. "
            "Run no InvestigationRunner with --investigate against this world: it picks up "
            "rejected incidents and would both race the second arm and spend outside the budget."
        ),
    )
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--ceiling",
        type=float,
        default=BUDGET_CEILING_USD,
        help="hard stop in USD; the registration fixes it at 25.00 and lowering it is allowed",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        help="restrict to these scenarios. For a dry check of the driver, not for the pilot",
    )
    parser.add_argument(
        "--settle",
        type=int,
        default=SETTLE_SECONDS,
        help="seconds to wait between pairs. The orchestrator's settle window is 300s and a pair "
        "started inside it is refused by the gate, so lowering this buys refusals, not speed",
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-user", default=os.environ.get("FAULTLINE_API_USER") or "faultline")
    parser.add_argument(
        "--i-have-read-the-registration",
        action="store_true",
        help="required. This command spends money and the registration says how much and why",
    )
    args = parser.parse_args(argv)

    if not args.i_have_read_the_registration:
        parser.error(
            "refusing to spend without --i-have-read-the-registration. "
            "evals/runs/PREREGISTRATION-Q53.md, section 4 is the budget."
        )
    if args.ceiling > BUDGET_CEILING_USD:
        parser.error(
            f"--ceiling {args.ceiling} is above the registered {BUDGET_CEILING_USD}. "
            "A budget revised upward mid-task is not a budget."
        )

    # **Everything the run needs, checked before a fault is injected.** Q20's rule, which this
    # repository has now re-learned four times: T6.3's second live run reached its model call and
    # died on a missing `anthropic`, after a fault had been injected, an incident opened and a
    # rejection recorded. Q53's own third dry run spent $0.79 and then discovered the second arm was
    # illegal. Both were knowable beforehand; this is where that knowing happens.
    #
    # `find_spec`, not an import - this module must stay unable to reach a model client at all
    # (`test_the_pilot_calls_no_model_itself`), and asking whether a package is installed is not
    # the same act as importing it.
    import importlib.util

    if importlib.util.find_spec("anthropic") is None:
        parser.error(
            "the `agents` extra is not installed here, so faultline-investigate cannot reach a "
            "model and every arm would produce nothing. Nothing was injected. "
            "Install it with: uv sync --all-extras --all-groups"
        )
    password = os.environ.get("FAULTLINE_API_PASSWORD") or ""
    if not password:
        parser.error(
            "FAULTLINE_API_PASSWORD is unset. The second arm of every pair is only legal after "
            "the incident passes through REJECTED, and the pilot gets it there through the "
            "authenticated route rather than by calling record_rejection. "
            "faultline-ingest must be running. See PREREGISTRATION-Q53.md, Amendment 1."
        )

    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{args.api_url.rstrip('/')}/openapi.json", timeout=10) as r:
            schema = json.loads(r.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        parser.error(
            f"cannot read {args.api_url}/openapi.json ({type(exc).__name__}: {exc}). "
            "faultline-ingest is not serving there, so the rejection between the arms would fail "
            "after the first arm had been paid for. Nothing was injected."
        )
    if not reject_route_is_mounted(schema):
        parser.error(
            f"{args.api_url} is serving, but {REJECT_PATH} is not among its routes: "
            "FAULTLINE_EXECUTOR_TOKEN_KEY is unset in that process, so api/app.py mounted the "
            "read surface and left the approve/reject routes off - and said so once, at startup. "
            "Every pair's second arm would 404 after the first arm was paid for. Nothing was "
            "injected."
        )

    scenarios = tuple(args.only) if args.only else SCENARIOS
    steps = LiveSteps(api_url=args.api_url, api_user=args.api_user, api_password=password)
    result = run_pilot(steps, scenarios, ceiling_usd=args.ceiling, settle=args.settle)
    print(result.render())
    if args.out:
        args.out.write_text(json.dumps(result.as_dict(), indent=2) + "\n")
        print(f"\n-> {args.out}")
    return 0
