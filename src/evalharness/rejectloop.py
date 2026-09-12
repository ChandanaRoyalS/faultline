"""The rejection loop, measured (T6.3, `PREREGISTRATION-T6.3.md` §4).

**The one question in T6.3 a test cannot answer**: does telling the agent *why* its fix was
rejected change the fix it proposes next? Everything else in the task is held by tests against a
scripted model at $0.00. This driver spends two model calls and records what came back.

## The protocol, which is §4.2's and is here so it cannot drift from it

Per incident: gate with the repair replay's patience; inject the scenario's fault; wait for the
incident to open; **seed the first proposal from dev sweep 12's recorded run**; reject it through
the real `POST /api/v1/incidents/{id}/reject` route with the reason fixed in the pre-registration;
run the re-investigation; record the second proposal, whether the rejection reached the proposer's
brief, and what it cost; `stop --all`; settle.

**The second proposal is not approved and not executed.** What is being measured is the loop's
effect on the proposal. Executing it would add a recovery measurement with n = 1 that the repair
replay already does properly, and would spend a second time to learn less.

## Three things this driver does deliberately

**The rejection goes over HTTP, through the route.** Calling `record_rejection` here would measure
a function; the claim is about the surface a person uses, and the surface is what T6.3 built. It
needs `faultline-ingest --postgres-dsn ...` running with the executor key set, which is also a
free end-to-end check of the write surface on a live world.

**The re-investigation is invoked here, not waited for.** The orchestrator's `InvestigationRunner`
would do it on a deployment; on a development machine it may not be running with `--investigate`,
and a driver that silently waited for something nobody started would look like an agent that had
nothing to say. `faultline-investigate <id>` as a subprocess is what the harness itself does.

**"The reason reached the agent" is read off the disclosure record**, not asserted. Every briefing
records which sections survived the budget (`briefing.as_row()`); `operator-rejection` in the
proposer's `kept` is the evidence that the section was in the brief the model saw, and it is
recorded by instrumentation that existed before this measurement wanted it.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = REPO_ROOT / "docs" / "evidence"

GATE_RETRY_SECONDS = 60
GATE_RETRIES = 10
SETTLE_SECONDS = 300


@dataclass(frozen=True)
class Pair:
    """One rejection, and the reason an operator types. **Fixed before the runs** - a reason
    chosen after seeing the second proposal would make this prompt-fitting."""

    scenario_id: str
    run_name: str
    reason: str
    why_it_is_earned: str


PAIRS: tuple[Pair, ...] = (
    Pair(
        scenario_id="redis-cart-dependency-latency",
        run_name="20260909T171220Z-redis-cart-dependency-latency",
        reason=(
            "Restarted cartservice and the alerts kept firing for the full window. The latency "
            "is on redis-cart's interface, not in cartservice's process."
        ),
        why_it_is_earned=(
            "T6.2's repair replay executed this proposal and the world did not recover: the "
            "first measured instance of the proposal's own failure row, *remediation proposed "
            "for the wrong service*."
        ),
    ),
    Pair(
        scenario_id="cart-dependency-latency",
        run_name="20260909T082922Z-cart-dependency-latency",
        reason=(
            "The executor refused: cartservice matches its declared definition in every "
            "field. Nothing about its configuration is wrong."
        ),
        why_it_is_earned=(
            "T6.2's repair replay refused this proposal on *no drift on environment, memory, "
            "nano_cpus*: the fault is a traffic-shaping sidecar and the fix was wrong in kind."
        ),
    ),
)
"""Both are proposals **T6.2 measured as failures**, so the rejection is a fact rather than a
staged opinion, and we know in advance what a better second proposal would look like."""


@dataclass
class Outcome:
    scenario_id: str
    incident_id: str | None = None
    first_action: str = ""
    first_target: str = ""
    second_action: str = ""
    second_target: str = ""
    rejection_reached_the_brief: bool = False
    dropped_sections: list[str] = field(default_factory=list)
    second_trajectory_id: str | None = None
    states: list[str] = field(default_factory=list)
    result: str = "pending"
    """`changed` | `unchanged` | `abstained` | `no-second-proposal` | `error` | `no-incident`."""
    reason: str = ""
    cost_usd: float | None = None
    started_at: str = ""
    finished_at: str = ""
    stop_all_reverted: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def advance_as_if_investigated(incident: Any, trajectory_id: str) -> list[str]:
    """Walk a seeded incident to `PROPOSING`, the way a real investigation would have.

    **Found by the first live run** (2026-09-12): the driver wrote the recorded proposal onto a
    trajectory and left the incident in `TRIAGING`, and the reject route refused it - *a proposal
    can be rejected from awaiting_approval, proposing, synthesizing only*. The route was right. An
    operator cannot reject a proposal on an incident that has never proposed anything, and adding
    `TRIAGING -> REJECTED` to ADR-0016's table so that a measurement could proceed would be
    changing the product to fit the instrument.

    What was wrong is that **seeding a proposal has to pretend the whole investigation happened**,
    not just its last artefact. `machine.INVESTIGATION_PHASES` is that walk and is not restated
    here: the same four transitions `record_agent_outcome` makes when a real run returns with a
    verdict and a proposal. The incident also takes the trajectory's id, because an incident whose
    `investigation_id` names nothing is one the screen cannot explain.

    The driver still spends nothing here. This is state, not a model call.
    """
    from faultline.orchestrator import machine

    incident.investigation_id = trajectory_id
    walked: list[str] = []
    for state, trigger in machine.INVESTIGATION_PHASES:
        machine.transition(incident, state, trigger=f"seeded: {trigger}")
        walked.append(state.value)
    return walked


class Steps(Protocol):
    def gate_admits(self) -> tuple[bool, list[str]]: ...

    def inject(self, scenario_id: str) -> str: ...

    def wait_for_incident(self, scenario_id: str, after: datetime) -> str | None: ...

    def seed_proposal(self, incident_id: str, run_dir: Path) -> dict[str, Any]:
        """Write the recorded proposal onto a trajectory for this incident. Returns it."""
        ...

    def reject(self, incident_id: str, reason: str) -> dict[str, Any]:
        """Through the route. Raises on anything but a 200."""
        ...

    def reinvestigate(self, incident_id: str) -> int: ...

    def second_proposal(self, incident_id: str, after_trajectory: str | None) -> dict[str, Any]:
        """The newest trajectory that is not `after_trajectory`, as a small dict: `proposal`,
        `kept`, `dropped`, `trajectory_id`, `states`, `cost_usd`."""
        ...

    def stop_all(self) -> list[str]: ...

    def sleep(self, seconds: float) -> None: ...

    def now(self) -> datetime: ...


def run_one(
    pair: Pair,
    run_dir: Path,
    steps: Steps,
    *,
    evidence_dir: Path,
    settle_seconds: int = SETTLE_SECONDS,
) -> Outcome:
    outcome = Outcome(scenario_id=pair.scenario_id, started_at=steps.now().isoformat())
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log = _Log(evidence_dir / "loop.log", steps)

    for attempt in range(1, GATE_RETRIES + 1):
        admits, refusals = steps.gate_admits()
        if admits:
            log.write("gate admitted")
            break
        log.write(f"gate refused (attempt {attempt}/{GATE_RETRIES}): {'; '.join(refusals)}")
        if attempt == GATE_RETRIES:
            outcome.result = "error"
            outcome.reason = "the gate never admitted"
            return _finish(outcome, steps, evidence_dir)
        steps.sleep(GATE_RETRY_SECONDS)

    began = steps.now()
    log.write(f"injecting {pair.scenario_id}")
    (evidence_dir / "inject.txt").write_text(steps.inject(pair.scenario_id))
    incident_id = steps.wait_for_incident(pair.scenario_id, began)
    if incident_id is None:
        outcome.result = "no-incident"
        outcome.reason = "no incident opened for the injected fault"
        steps.stop_all()
        return _finish(outcome, steps, evidence_dir)
    outcome.incident_id = incident_id
    log.write(f"incident {incident_id}")

    seeded = steps.seed_proposal(incident_id, run_dir)
    outcome.first_action = str(seeded.get("action_id") or "")
    outcome.first_target = str(seeded.get("target") or "")
    first_trajectory = str(seeded.get("trajectory_id") or "") or None
    outcome.states += [str(s) for s in seeded.get("states") or []]
    (evidence_dir / "first-proposal.json").write_text(json.dumps(seeded, indent=2, sort_keys=True))
    log.write(
        f"seeded the recorded proposal: {outcome.first_action} -> {outcome.first_target}; "
        f"incident walked to {outcome.states[-1] if outcome.states else 'nowhere'}"
    )

    try:
        rejected = steps.reject(incident_id, pair.reason)
    except Exception as exc:  # recorded, never swallowed
        outcome.result = "error"
        outcome.reason = f"the reject route refused: {type(exc).__name__}: {exc}"
        log.write(outcome.reason)
        steps.stop_all()
        return _finish(outcome, steps, evidence_dir)
    (evidence_dir / "rejection.json").write_text(json.dumps(rejected, indent=2, sort_keys=True))
    outcome.states.append(str(rejected.get("state") or ""))
    log.write(f"rejected through the route: {rejected.get('state')}")

    # **The model call.** One re-investigation, invoked the way the harness invokes one.
    code = steps.reinvestigate(incident_id)
    log.write(f"faultline-investigate exited {code}")

    second = steps.second_proposal(incident_id, first_trajectory)
    (evidence_dir / "second.json").write_text(json.dumps(second, indent=2, sort_keys=True))
    outcome.second_trajectory_id = second.get("trajectory_id")
    outcome.cost_usd = second.get("cost_usd")
    outcome.states += [str(s) for s in second.get("states") or []]
    outcome.rejection_reached_the_brief = "operator-rejection" in (second.get("kept") or [])
    outcome.dropped_sections = [str(d) for d in second.get("dropped") or []]
    proposal = dict(second.get("proposal") or {})
    if not proposal:
        outcome.result = "no-second-proposal"
        outcome.reason = "the re-investigation produced no proposal"
    else:
        outcome.second_action = str(proposal.get("action_id") or "")
        outcome.second_target = str(proposal.get("target") or "")
        if not outcome.second_action:
            outcome.result = "abstained"
            outcome.reason = "remediation_class none - no permitted action fits the evidence"
        elif (outcome.second_action, outcome.second_target) == (
            outcome.first_action,
            outcome.first_target,
        ):
            outcome.result = "unchanged"
            outcome.reason = "the same action against the same target"
        else:
            outcome.result = "changed"
            outcome.reason = (
                f"{outcome.first_action} -> {outcome.first_target} became "
                f"{outcome.second_action} -> {outcome.second_target}"
            )
    log.write(f"second proposal: {outcome.result} ({outcome.reason})")

    outcome.stop_all_reverted = steps.stop_all()
    log.write(f"stop --all reverted {outcome.stop_all_reverted or 'nothing'}")
    if settle_seconds:
        log.write(f"settling {settle_seconds}s")
        steps.sleep(settle_seconds)
    return _finish(outcome, steps, evidence_dir)


def _finish(outcome: Outcome, steps: Steps, evidence_dir: Path) -> Outcome:
    outcome.finished_at = steps.now().isoformat()
    (evidence_dir / "outcome.json").write_text(
        json.dumps(outcome.as_dict(), indent=2, sort_keys=True)
    )
    return outcome


class _Log:
    def __init__(self, path: Path, steps: Steps) -> None:
        self._path = path
        self._steps = steps

    def write(self, line: str) -> None:
        stamped = f"{self._steps.now().isoformat()} {line}"
        print(f"  {stamped}", flush=True)
        with self._path.open("a") as handle:
            handle.write(stamped + "\n")


def summary(outcomes: list[Outcome]) -> str:
    """What §4.3 says is scored, and nothing it does not. **n = 2, R = 1**, stated at the top so
    the number cannot be lifted out of the table and quoted as a rate."""
    changed = [o for o in outcomes if o.result in {"changed", "abstained"}]
    reached = [o for o in outcomes if o.rejection_reached_the_brief]
    spend = sum(o.cost_usd or 0.0 for o in outcomes)
    lines = [
        "# The rejection loop — does telling the agent why change what it proposes?",
        "",
        "`PREREGISTRATION-T6.3.md` §4. **An existence demonstration, not a rate**: n = 2, R = 1, "
        "and both scenarios were chosen because T6.2 measured their proposals as failures. No "
        "figure here belongs beside a sweep's.",
        "",
        f"**The reason reached the proposer in {len(reached)} of {len(outcomes)}.** "
        f"{len(changed)} of {len(outcomes)} second proposals differed from the first "
        f"(an abstention counts as differing: it is the proposer declining, which is a valid "
        f"proposal and here may be the correct one).",
        "",
        f"Model spend: **${spend:.2f}**.",
        "",
        "| scenario | first proposal | second proposal | reason in the brief? | outcome |",
        "|---|---|---|---|---|",
    ]
    for o in outcomes:
        second = (
            f"`{o.second_action}` → {o.second_target}"
            if o.second_action
            else ("*abstained*" if o.result == "abstained" else "*none*")
        )
        lines.append(
            f"| {o.scenario_id} | `{o.first_action}` → {o.first_target} | {second} | "
            f"{'yes' if o.rejection_reached_the_brief else '**no**'} | **{o.result}** |"
        )
    return "\n".join(lines) + "\n"


class RealSteps:
    """The live world, the real route, and one `faultline-investigate` per rejection."""

    def __init__(self, dsn: str, api_url: str, api_user: str, api_password: str) -> None:
        self._dsn = dsn
        self._api = api_url.rstrip("/")
        self._auth = base64.b64encode(f"{api_user}:{api_password}".encode()).decode()
        """Built once and never logged. The password arrives in the environment and leaves in a
        header; it is in no file this driver writes."""

    # --- the world ---------------------------------------------------------------

    def gate_admits(self) -> tuple[bool, list[str]]:
        from evalharness import gate

        reading = gate.read(runs_remaining=1)
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

    def stop_all(self) -> list[str]:
        from injector.engine import Engine
        from injector.settings import InjectorSettings

        engine = Engine(InjectorSettings())
        active = list(engine.active())
        for fault in active:
            engine.stop(fault)
        return active

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def now(self) -> datetime:
        return datetime.now(UTC)

    # --- the proposal under rejection --------------------------------------------

    def seed_proposal(self, incident_id: str, run_dir: Path) -> dict[str, Any]:
        """**The registered deviation** (§4.2): the first proposal is the one dev sweep 12's agent
        wrote for this scenario, written onto a trajectory for this incident rather than produced
        by a live investigation. Same agent, same scenario, same stamp; what is not paid for is
        the first $0.71. The alternative buys only that the prior text came from this hour."""
        import psycopg

        from faultline.agents.stamp import runtime_version
        from faultline.agents.trajectory import (
            PostgresTrajectoryStore,
            StepKind,
            Trajectory,
            TrajectoryStep,
        )

        verdicts = sorted(run_dir.glob("*-verdict.json"))
        if not verdicts:
            raise FileNotFoundError(f"{run_dir} holds no *-verdict.json")
        recorded = json.loads(verdicts[0].read_text())
        proposal = dict(recorded.get("proposal") or {})
        if not proposal.get("action_id"):
            raise RuntimeError(f"{run_dir.name}: the recorded proposal is an abstention")

        trajectory = Trajectory(
            incident_id=incident_id,
            model=str(recorded.get("model") or "recorded"),
            effort="medium",
            started_at=self.now(),
            runtime_version=runtime_version(),
        )
        trajectory.add(
            TrajectoryStep(
                seq=1,
                kind=StepKind.PROPOSAL,
                role="proposer",
                at=self.now(),
                payload={
                    "proposal": proposal,
                    "accepted": True,
                    "attempts": 1,
                    "violations": [],
                    "escalated": False,
                    # Marked, so that nobody reading this trajectory later mistakes it for a live
                    # investigation of this incident. It is one recorded proposal and no evidence.
                    "seeded_from": run_dir.name,
                },
            )
        )
        PostgresTrajectoryStore(psycopg.connect(self._dsn)).save(trajectory)

        from faultline.orchestrator.store import PostgresIncidentStore

        incidents = PostgresIncidentStore(psycopg.connect(self._dsn))
        incident = incidents.get(incident_id)
        if incident is None:
            raise RuntimeError(f"incident {incident_id} vanished between opening and seeding")
        walked = advance_as_if_investigated(incident, trajectory.id)
        incidents.save_investigation_state(incident)
        return {**proposal, "trajectory_id": trajectory.id, "states": walked}

    # --- the route ---------------------------------------------------------------

    def reject(self, incident_id: str, reason: str) -> dict[str, Any]:
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
            with urllib.request.urlopen(request, timeout=30) as response:
                return dict(json.loads(response.read().decode() or "{}"))
        except urllib.error.HTTPError as failure:
            raise RuntimeError(
                f"{failure.code}: {failure.read().decode(errors='replace')[:400]}"
            ) from None

    # --- the model call ------------------------------------------------------------

    def reinvestigate(self, incident_id: str) -> int:
        from evalharness.run import _sh

        code, out = _sh(["faultline-investigate", incident_id])
        print(out)
        return code

    def second_proposal(self, incident_id: str, after_trajectory: str | None) -> dict[str, Any]:
        import psycopg

        from faultline.agents.trajectory import PostgresTrajectoryStore

        store = PostgresTrajectoryStore(psycopg.connect(self._dsn))
        trajectory = store.latest_for_incident(incident_id)
        if trajectory is None or trajectory.id == after_trajectory:
            return {}
        proposal: dict[str, Any] = {}
        kept: list[str] = []
        dropped: list[str] = []
        for step in trajectory.steps:
            payload = dict(step.payload or {})
            if payload.get("proposal"):
                proposal = dict(payload["proposal"])
            disclosure = payload.get("disclosure")
            if isinstance(disclosure, dict):
                for brief in disclosure.get("briefings") or []:
                    if isinstance(brief, dict) and brief.get("role") == "proposer":
                        kept = [str(k) for k in brief.get("kept") or []]
                        dropped = [str(d) for d in brief.get("dropped") or []]
        # **Priced the way every other run in this repository is priced** - the trajectory's own
        # token counts at `evalharness.run`'s constants - rather than with a second formula that
        # could drift from the one `RESULTS.md` was computed with.
        from evalharness.run import USD_PER_MTOK_IN, USD_PER_MTOK_OUT

        tokens_in = sum(int(step.tokens_in or 0) for step in trajectory.steps)
        tokens_out = sum(int(step.tokens_out or 0) for step in trajectory.steps)
        cost = tokens_in / 1e6 * USD_PER_MTOK_IN + tokens_out / 1e6 * USD_PER_MTOK_OUT
        return {
            "trajectory_id": trajectory.id,
            "proposal": proposal,
            "kept": kept,
            "dropped": dropped,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": round(cost, 4),
            "states": [],
        }


def run_cli(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="faultline-reject-loop",
        description="Reject a recorded proposal through the real route and measure what the "
        "agent proposes next (T6.3 §4). Spends one model call per pair.",
    )
    p.add_argument("--only", action="append", default=None, help="scenario id(s)")
    p.add_argument("--attempt", default=None, help="label for a re-attempt")
    p.add_argument("--api-url", default="http://127.0.0.1:8000")
    p.add_argument("--api-user", default=os.environ.get("FAULTLINE_API_USER") or "faultline")
    p.add_argument("--postgres-dsn", default=None)
    p.add_argument("--evidence-root", default=str(EVIDENCE_ROOT))
    p.add_argument("--settle", type=int, default=SETTLE_SECONDS)
    args = p.parse_args(argv)

    password = os.environ.get("FAULTLINE_API_PASSWORD") or ""
    if not password:
        p.error(
            "FAULTLINE_API_PASSWORD is unset - the rejection goes through the authenticated "
            "route, which is the surface being measured"
        )

    from faultline.orchestrator.settings import OrchestratorSettings

    dsn = args.postgres_dsn or OrchestratorSettings().postgres_dsn
    steps: Steps = RealSteps(dsn, args.api_url, args.api_user, password)
    pairs = [pair for pair in PAIRS if not args.only or pair.scenario_id in args.only]
    root = Path(args.evidence_root)
    suffix = f".{args.attempt}" if args.attempt else ""
    # Captured evidence is never rewritten - the replay driver's rule, and for the same reason.
    planned = [
        (pair, root / "t6.3-rejection-loop" / f"{pair.scenario_id}{suffix}") for pair in pairs
    ]
    taken = [str(d) for _, d in planned if d.exists() and any(d.iterdir())]
    if taken:
        p.error(
            "evidence already captured, refusing to rewrite it: "
            + ", ".join(taken)
            + " (name this run with --attempt <label>)"
        )

    outcomes: list[Outcome] = []
    for index, (pair, evidence_dir) in enumerate(planned, 1):
        print(f"=== [{index}/{len(planned)}] {pair.scenario_id} <- {pair.run_name}", flush=True)
        print(f"    rejecting because: {pair.reason}", flush=True)
        outcome = run_one(
            pair,
            REPO_ROOT / "evals" / "runs" / pair.run_name,
            steps,
            evidence_dir=evidence_dir,
            settle_seconds=args.settle,
        )
        outcomes.append(outcome)
        print(f"    -> {outcome.result} {outcome.reason}".rstrip(), flush=True)

    out = root / "t6.3-rejection-loop"
    out.mkdir(parents=True, exist_ok=True)
    only = f".{'+'.join(sorted(args.only))}" if args.only else ""
    (out / f"LOOP{only}{suffix}.md").write_text(summary(outcomes))
    print(summary(outcomes))
    return 0 if all(o.result != "error" for o in outcomes) else 1
