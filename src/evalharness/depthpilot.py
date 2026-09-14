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

    @property
    def complete(self) -> bool:
        return len(self.verdicts) == 2

    @property
    def differs(self) -> bool:
        """**The pilot's whole outcome.** A changed `fault_class` or `remediation_class`.

        Not "is it better": that is the 30-40 pair measurement this pilot exists to decide whether
        to fund. `n = 10` cannot say which direction dominates and the registration forbids
        reporting it as if it could.
        """
        if not self.complete:
            return False
        a, b = self.verdicts[BASELINE_ARM], self.verdicts[CHANGE_ARM]
        return (a.fault_class, a.remediation_class) != (b.fault_class, b.remediation_class)

    @property
    def cost_usd(self) -> float:
        return sum(v.cost_usd for v in self.verdicts.values())


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
            if pair.skipped:
                lines.append(f"  {pair.scenario_id}: skipped - {pair.skipped}")
                continue
            mark = "DIFFERS" if pair.differs else "same" if pair.complete else "incomplete"
            detail = ", ".join(
                f"{arm}={v.fault_class}/{v.remediation_class}"
                for arm, v in sorted(pair.verdicts.items())
            )
            lines.append(f"  {pair.scenario_id}: {mark}  first={pair.first_arm}  {detail}")
        if not self.stopped and self.complete_pairs and not self.differing:
            lines.append("")
            lines.append(
                "0 of "
                f"{len(self.complete_pairs)} differ. Per PREREGISTRATION-Q53.md 3.2 this closes "
                "Q53: the effect is below the retrieval upper bound at 87% confidence and the "
                "larger measurement is not funded."
            )
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "stopped": self.stopped,
            "cost_usd": round(self.cost_usd, 4),
            "ceiling_usd": BUDGET_CEILING_USD,
            "arms": ARMS,
            "pairs": [
                {
                    "scenario_id": p.scenario_id,
                    "incident_id": p.incident_id,
                    "first_arm": p.first_arm,
                    "skipped": p.skipped,
                    "complete": p.complete,
                    "differs": p.differs,
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
    for index, scenario_id in enumerate(scenarios):
        if index and settle:
            print(f"--- settling {settle}s before {scenario_id}", flush=True)
            nap(settle)
        pair = PairResult(scenario_id=scenario_id)
        result.pairs.append(pair)

        if result.cost_usd >= ceiling_usd:
            result.stopped = f"budget ceiling ${ceiling_usd:.2f} reached before {scenario_id}"
            pair.skipped = "budget"
            break

        admitted, refusals = steps.gate_admits()
        if not admitted:
            pair.skipped = f"gate refused: {'; '.join(refusals)}"
            continue

        started = datetime.now(UTC)
        steps.inject(scenario_id)
        try:
            incident_id = steps.wait_for_incident(scenario_id, started)
            if not incident_id:
                pair.skipped = "no incident"
                continue
            pair.incident_id = incident_id

            first, second = arm_order(index)
            pair.first_arm = first
            for arm in (first, second):
                if result.cost_usd >= ceiling_usd:
                    result.stopped = f"budget ceiling ${ceiling_usd:.2f} reached in {scenario_id}"
                    break
                verdict = steps.investigate(incident_id, arm)
                if verdict is None:
                    pair.skipped = f"{arm} produced no verdict"
                    break
                pair.verdicts[arm] = verdict
        finally:
            steps.revert(scenario_id)

        if result.stopped:
            break
    return result


class LiveSteps:  # pragma: no cover - the paid path; the fakes cover the logic
    """The real world. Every operation is the harness's own, never a reimplementation.

    `faultline-investigate` is shelled rather than imported, for the reason Q53's registration
    gives: the two arms have to be **the pipeline**, and a driver that constructed an
    `Investigation` itself would be measuring a second implementation that happens to live in the
    same repository. It is also what lets `env_for` vary the configuration at all.
    """

    def __init__(self, dsn: str | None = None) -> None:
        from faultline.context.settings import ContextSettings

        self._dsn = dsn or ContextSettings().postgres_dsn

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
            "kill switch, not a measurement, and it adopts nothing whatever it finds."
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

    scenarios = tuple(args.only) if args.only else SCENARIOS
    result = run_pilot(LiveSteps(), scenarios, ceiling_usd=args.ceiling, settle=args.settle)
    print(result.render())
    if args.out:
        args.out.write_text(json.dumps(result.as_dict(), indent=2) + "\n")
        print(f"\n-> {args.out}")
    return 0
