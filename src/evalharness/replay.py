"""The repair replay (T6.2, `PREREGISTRATION-T6.2.md` §4): do the agent's fixes work when executed?

**A different benchmark from diagnosis, and this module is the wall between them.** Every fix-class
figure in the repository means *the agent named a fix* (ADR-0028 §4). This measures something else:
whether the fix an agent already named, in a run already scored, restores the world when a human
approves it and the executor performs it. It is T7.50 §4's design C - repair scored apart - and it
is not a loop: the agent that wrote each proposal finished days ago, no agent runs here, and
nothing observed re-enters any context. `runtime_version` does not move; no run directory is
touched; `faultline-eval-db load` sees nothing new. Prediction 8 is a test of exactly that.

**What one replay is**, per triple (scenario, action, target) - the protocol the pre-registration
fixed, in its order:

1. the baseline gate admits (`faultline-gate`'s reading; refusals wait and retry, like the sweep);
2. inject the scenario's fault; wait for the orchestrator to open the incident, which stays in
   `TRIAGING` because no investigation is run;
3. approve the recorded proposal against this incident (`faultline-approve --from-run`, in-process)
   and execute it;
4. score, in order of precedence: **refused** with the executor's reason; **executed, recovered**
   - no alert firing within the proposal's own `confirm_within_seconds` and the injector reporting
   the fault no longer in force; **executed, not recovered**; **error**;
5. `faultline-inject stop --all` - a no-op after a recovery, and the test of ADR-0038 §3's
   coupling - then the sweep's settle.

**No model call anywhere.** `faultline-approve` reads a JSON file; the executor runs one compose
command. Any model call in this module is a defect (prediction 10).

The steps are behind `Steps`, a seam: `RealSteps` is the harness, the executor and the injector;
`tests/test_replay.py` substitutes a fake and exercises the driver's decisions - the scoring
precedence, the evidence written, the proof's three refusals - without a world.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = REPO_ROOT / "docs" / "evidence"

TRIPLES: tuple[tuple[str, str], ...] = (
    ("shipping-wrong-image", "20260909T105155Z-shipping-wrong-image"),
    ("cart-bad-image-tag", "20260909T151114Z-cart-bad-image-tag"),
    ("cart-redis-misconfig", "20260909T154920Z-cart-redis-misconfig"),
    ("shipping-quote-misconfig", "20260909T140204Z-shipping-quote-misconfig"),
    ("payment-telemetry-blackout", "20260909T163025Z-payment-telemetry-blackout"),
    ("frauddetection-memory-squeeze", "20260909T160827Z-frauddetection-memory-squeeze"),
    ("ad-memory-squeeze", "20260909T111957Z-ad-memory-squeeze"),
    ("cart-dependency-latency", "20260909T082922Z-cart-dependency-latency"),
    ("redis-cart-dependency-latency", "20260909T171220Z-redis-cart-dependency-latency"),
)
"""The nine distinct (scenario, action, target) proposals dev sweep 12's arm A recorded, one run
directory each - the most recent run proposing that triple, so the proposal text is the latest the
agent wrote. `PREREGISTRATION-T6.2.md` §4.1 is the table; `tests/test_replay.py` checks these
directories exist and carry the action and target the table says."""

SETTLE_SECONDS = 300
"""The sweep's, for the same reason: the orchestrator's settle window."""


@dataclass(slots=True)
class Outcome:
    scenario_id: str
    run_dir: str
    action_id: str
    target: str
    incident_id: str | None = None
    token_id: str | None = None
    audit_id: str | None = None
    executed: bool = False
    result: str = ""
    """`refused`, `recovered`, `not-recovered`, `error`, or `no-incident` (the world did not
    alert, and the executor was never asked)."""

    reason: str = ""
    confirm_within_seconds: int = 0
    alerts_cleared_after_seconds: int | None = None
    fault_in_force_after: bool | None = None
    stop_all_reverted: list[str] = field(default_factory=list)
    """Fault ids `stop --all` found active afterwards. Empty after a recovery is the coupling
    holding; a name here after a recovery is ADR-0038 §3 unbuilt (prediction 3)."""

    started_at: str = ""
    finished_at: str = ""
    refusals: list[dict[str, Any]] = field(default_factory=list)
    """The proof's three refusals (`--proof`): replayed token, kill switch, wrong target."""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Steps(Protocol):
    """Everything the driver does to the world, so the driver can be tested without one."""

    def gate_admits(self) -> tuple[bool, list[str]]: ...

    def inject(self, scenario_id: str) -> str: ...

    def wait_for_incident(self, scenario_id: str, after: datetime) -> str | None: ...

    def approve(
        self, incident_id: str, run_dir: Path, *, target_override: str | None = None
    ) -> tuple[str, dict[str, Any]]:
        """Returns the token and the approval's audit row."""
        ...

    def execute(self, token: str, *, kill_switch: bool = False) -> dict[str, Any]: ...

    def firing_alerts(self) -> list[str]: ...

    def fault_in_force(self, scenario_id: str) -> bool: ...

    def stop_all(self) -> list[str]:
        """Fault ids that were active and got reverted."""
        ...

    def sleep(self, seconds: float) -> None: ...

    def now(self) -> datetime: ...


GATE_RETRY_SECONDS = 60
GATE_RETRIES = 10


def replay_one(
    scenario_id: str,
    run_dir: Path,
    steps: Steps,
    *,
    evidence_dir: Path,
    proof: bool = False,
    settle_seconds: int = SETTLE_SECONDS,
    poll_seconds: int = 15,
) -> Outcome:
    proposal = _recorded_proposal(run_dir)
    outcome = Outcome(
        scenario_id=scenario_id,
        run_dir=run_dir.name,
        action_id=str(proposal.get("action_id") or ""),
        target=str(proposal.get("target") or ""),
        confirm_within_seconds=int(proposal.get("confirm_within_seconds") or 0),
        started_at=steps.now().isoformat(),
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log = _Log(evidence_dir / "replay.log", steps)

    # 1. the gate, with the sweep's patience
    for attempt in range(1, GATE_RETRIES + 1):
        admitted, refusals = steps.gate_admits()
        if admitted:
            break
        log.write(f"gate refused (attempt {attempt}/{GATE_RETRIES}): {'; '.join(refusals)}")
        if attempt == GATE_RETRIES:
            outcome.result = "no-incident"
            outcome.reason = "the baseline gate never admitted a run: " + "; ".join(refusals)
            return _finish(outcome, steps, evidence_dir)
        steps.sleep(GATE_RETRY_SECONDS)
    log.write("gate admitted")

    # 2. inject and wait
    injected_at = steps.now()
    log.write(f"injecting {scenario_id}")
    (evidence_dir / "inject.txt").write_text(steps.inject(scenario_id))
    incident_id = steps.wait_for_incident(scenario_id, injected_at)
    if incident_id is None:
        outcome.result = "no-incident"
        outcome.reason = "the world did not open an incident for this injection"
        log.write(outcome.reason)
        outcome.stop_all_reverted = steps.stop_all()
        return _finish(outcome, steps, evidence_dir)
    outcome.incident_id = incident_id
    log.write(f"incident {incident_id} opened; no investigation is run")

    # 3. approve and execute
    token, approval = steps.approve(incident_id, run_dir)
    outcome.token_id = approval.get("token_id")
    (evidence_dir / "approval.json").write_text(json.dumps(approval, indent=2, sort_keys=True))
    log.write(f"approved {outcome.action_id} -> {outcome.target}; token {outcome.token_id}")
    # The proof's two extra tokens are minted **now**, while the incident is AWAITING_APPROVAL and
    # a further approval is idempotent. The second proof run minted them after the execution, the
    # incident was EXECUTING, and ADR-0016's table refused EXECUTING -> AWAITING_APPROVAL -
    # correctly (one action per incident, ADR-0028 §5) - which crashed the driver mid-proof.
    proof_tokens: tuple[str, str] | None = None
    if proof:
        fresh, _ = steps.approve(incident_id, run_dir)
        wrong, _ = steps.approve(incident_id, run_dir, target_override="paymentservice")
        proof_tokens = (fresh, wrong)
        log.write("proof: minted the kill-switch and wrong-target tokens ahead of the execution")
    executed_at = steps.now()
    record = steps.execute(token)
    outcome.audit_id = record.get("id")
    (evidence_dir / "audit.json").write_text(json.dumps(record, indent=2, sort_keys=True))
    log.write(f"executor: {record.get('outcome')} {record.get('reason') or ''}".rstrip())

    # 4. score
    if record.get("outcome") in ("refused", "kill_switch"):
        outcome.result = "refused"
        outcome.reason = str(record.get("reason") or "")
    elif record.get("outcome") == "error":
        outcome.executed = True
        outcome.result = "error"
        outcome.reason = str(record.get("reason") or "")
    else:
        outcome.executed = True
        # **The proof's refusals come before the recovery wait, not after it** (2026-09-11). The
        # first run presented the replayed token and the wrong-target token after the world had
        # recovered - by which time the orchestrator had resolved the incident, and the executor
        # refused both at step 3 ("incident is resolved") before single-use or scope were ever
        # reached. Three refusals fired and two of them demonstrated the wrong property. Presented
        # here, while the incident is `EXECUTING`, they are refused for the reasons they exist to
        # show: *already spent* and *outside the incident's scope*.
        if proof and proof_tokens is not None:
            outcome.refusals = _proof_refusals(steps, token, *proof_tokens, log)
            (evidence_dir / "refusals.json").write_text(
                json.dumps(outcome.refusals, indent=2, sort_keys=True)
            )
        cleared = _wait_for_quiet(steps, outcome.confirm_within_seconds, poll_seconds, log)
        outcome.alerts_cleared_after_seconds = (
            None if cleared is None else int((cleared - executed_at).total_seconds())
        )
        outcome.fault_in_force_after = steps.fault_in_force(scenario_id)
        recovered = cleared is not None and not outcome.fault_in_force_after
        outcome.result = "recovered" if recovered else "not-recovered"
        if not recovered:
            outcome.reason = (
                f"alerts {'cleared' if cleared else 'still firing'} after "
                f"{outcome.confirm_within_seconds}s; fault "
                f"{'still' if outcome.fault_in_force_after else 'not'} in force"
            )
        log.write(f"scored {outcome.result} {outcome.reason}".rstrip())

    # 5. revert whatever is left, then settle
    outcome.stop_all_reverted = steps.stop_all()
    log.write(f"stop --all reverted: {outcome.stop_all_reverted or 'nothing'}")
    if outcome.executed and outcome.result == "recovered" and outcome.stop_all_reverted:
        log.write("WARNING: stop --all reverted something after a recovery - ADR-0038 §3 coupling")
    log.write(f"settling {settle_seconds}s")
    steps.sleep(settle_seconds)
    return _finish(outcome, steps, evidence_dir)


def _wait_for_quiet(steps: Steps, window: int, poll: int, log: _Log) -> datetime | None:
    """The moment no alert was firing, or None if the window elapsed first."""
    deadline = steps.now().timestamp() + window
    while True:
        firing = steps.firing_alerts()
        if not firing:
            return steps.now()
        if steps.now().timestamp() >= deadline:
            log.write(f"window of {window}s elapsed; still firing: {firing}")
            return None
        steps.sleep(poll)


def _proof_refusals(
    steps: Steps, spent_token: str, fresh_token: str, wrong_token: str, log: _Log
) -> list[dict[str, Any]]:
    """`PREREGISTRATION-T6.2.md` §3: the same token again, the kill switch, the wrong target.

    Each presentation is its own try: a refusal step that raises is recorded as an `error` entry
    and the next one still runs, because a proof that dies on its second check has proved one
    thing and recorded nothing about the other two - which is what happened on 2026-09-11."""
    refusals: list[dict[str, Any]] = []
    for check, presented, kill_switch in (
        ("replayed token", spent_token, False),
        ("kill switch", fresh_token, True),
        ("wrong target", wrong_token, False),
    ):
        try:
            result = steps.execute(presented, kill_switch=kill_switch)
        except Exception as exc:  # recorded, never swallowed
            result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        refusals.append({"check": check, **result})
        log.write(f"{check}: {result.get('outcome')} - {result.get('reason')}")
    return refusals


def _finish(outcome: Outcome, steps: Steps, evidence_dir: Path) -> Outcome:
    outcome.finished_at = steps.now().isoformat()
    (evidence_dir / "outcome.json").write_text(
        json.dumps(outcome.as_dict(), indent=2, sort_keys=True)
    )
    return outcome


def _recorded_proposal(run_dir: Path) -> dict[str, Any]:
    verdicts = sorted(run_dir.glob("*-verdict.json"))
    if not verdicts:
        raise FileNotFoundError(f"{run_dir} holds no *-verdict.json")
    return dict(json.loads(verdicts[0].read_text()).get("proposal") or {})


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
    """`REPLAY.md`: the aggregate the pre-registration §4.3 says may be quoted - recovered over
    executed, with every refusal listed by reason beside it, never folded in."""
    executed = [o for o in outcomes if o.executed]
    recovered = [o for o in executed if o.result == "recovered"]
    refused = [o for o in outcomes if o.result == "refused"]
    errors = [o for o in executed if o.result == "error"]
    lines = [
        "# Repair replay — dev sweep 12's proposals, executed",
        "",
        "Scored apart from diagnosis (`PREREGISTRATION-T6.2.md` §4). R = 1 on a deterministic "
        "operation; the proposals were written by an agent that could not act and had finished. "
        "**No model call was made.**",
        "",
        f"**Recovered {len(recovered)} of {len(executed)} executed**; {len(refused)} refused; "
        f"{len(errors)} error(s); n = {len(outcomes)} triples.",
        "",
        "| scenario | action → target | result | detail |",
        "|---|---|---|---|",
    ]
    for o in outcomes:
        detail = o.reason
        if o.result == "recovered":
            detail = (
                f"alerts clear after {o.alerts_cleared_after_seconds}s of "
                f"{o.confirm_within_seconds}s"
            )
        if o.executed and o.stop_all_reverted:
            detail += f"; stop --all still reverted {o.stop_all_reverted}"
        lines.append(
            f"| {o.scenario_id} | `{o.action_id}` → {o.target} | **{o.result}** | {detail} |"
        )
    if refused:
        lines += [
            "",
            "Refusals are facts about the executor's model of the world or about the "
            "proposer's target, not about whether the fix would have worked:",
            "",
        ]
        lines += [f"- **{o.scenario_id}**: {o.reason}" for o in refused]
    return "\n".join(lines) + "\n"


class RealSteps:
    """The harness, the executor and the injector, wired to the live world."""

    def __init__(self, dsn: str) -> None:
        from faultline.executor.settings import ExecutorSettings

        self._dsn = dsn
        self._settings = ExecutorSettings().model_copy(update={"postgres_dsn": dsn})
        if not self._settings.token_key.get_secret_value():
            raise SystemExit(
                "REFUSED: FAULTLINE_EXECUTOR_TOKEN_KEY is unset. The replay mints and verifies "
                "tokens; export a session key first: "
                'export FAULTLINE_EXECUTOR_TOKEN_KEY="$(openssl rand -hex 32)"'
            )

    def _stores(self) -> tuple[Any, Any]:
        import psycopg

        from faultline.executor.audit import PostgresAuditStore
        from faultline.orchestrator.store import PostgresIncidentStore

        conn = psycopg.connect(self._dsn)
        return PostgresIncidentStore(conn), PostgresAuditStore(conn)

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

    def approve(
        self, incident_id: str, run_dir: Path, *, target_override: str | None = None
    ) -> tuple[str, dict[str, Any]]:
        import getpass

        from faultline.context.allowlist import load_allowlist
        from faultline.executor.cli import approve

        incidents, audit = self._stores()
        proposal = _recorded_proposal(run_dir)
        if target_override:
            proposal = {**proposal, "target": target_override}
        token, record = approve(
            incident_id=incident_id,
            incidents=incidents,
            audit=audit,
            settings=self._settings,
            catalog=load_allowlist(),
            proposal=proposal,
            proposal_id=run_dir.name,
            caller=f"{getpass.getuser()} (repair replay)",
        )
        return token, record.as_dict()

    def execute(self, token: str, *, kill_switch: bool = False) -> dict[str, Any]:
        from faultline.executor.core import Executor, World

        incidents, audit = self._stores()
        executor = Executor(
            key=self._settings.token_key.get_secret_value(),
            kill_switch=kill_switch,
            incidents=incidents,
            audit=audit,
            world=World(),
        )
        return executor.execute(token, caller="repair replay").as_dict()

    def firing_alerts(self) -> list[str]:
        from evalharness.prom import firing_alerts

        return list(firing_alerts())

    def fault_in_force(self, scenario_id: str) -> bool:
        from injector.engine import Engine
        from injector.settings import InjectorSettings

        return scenario_id in Engine(InjectorSettings()).active()

    def stop_all(self) -> list[str]:
        from injector.engine import Engine
        from injector.settings import InjectorSettings

        return [r.fault_id for r in Engine(InjectorSettings()).stop_all() if r.was_active]

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def now(self) -> datetime:
        return datetime.now(UTC)


def run_cli(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="faultline-replay",
        description="Execute dev sweep 12's recorded proposals against fresh injections (T6.2 §4).",
    )
    p.add_argument("--only", action="append", default=None, help="scenario id(s) to replay")
    p.add_argument(
        "--proof",
        action="store_true",
        help="after the first executed action, present the three refusals the pre-registration "
        "names (replayed token, kill switch, wrong target); evidence to t6.2-first-execution/",
    )
    p.add_argument("--postgres-dsn", default=None)
    p.add_argument("--evidence-root", default=str(EVIDENCE_ROOT))
    p.add_argument("--settle", type=int, default=SETTLE_SECONDS)
    args = p.parse_args(argv)

    from faultline.orchestrator.settings import OrchestratorSettings

    dsn = args.postgres_dsn or OrchestratorSettings().postgres_dsn
    steps = RealSteps(dsn)
    triples = [(s, r) for s, r in TRIPLES if not args.only or s in args.only]
    root = Path(args.evidence_root)
    outcomes: list[Outcome] = []
    for index, (scenario_id, run_name) in enumerate(triples, 1):
        print(f"=== [{index}/{len(triples)}] {scenario_id} <- {run_name}", flush=True)
        run_dir = REPO_ROOT / "evals" / "runs" / run_name
        is_proof = args.proof and index == 1
        evidence_dir = (
            root / ("t6.2-first-execution" if is_proof else "t6.2-repair-replay") / scenario_id
        )
        outcome = replay_one(
            scenario_id,
            run_dir,
            steps,
            evidence_dir=evidence_dir,
            proof=is_proof,
            settle_seconds=args.settle,
        )
        outcomes.append(outcome)
        print(f"    -> {outcome.result} {outcome.reason}".rstrip(), flush=True)
    (root / "t6.2-repair-replay" / "REPLAY.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "t6.2-repair-replay" / "REPLAY.md").write_text(summary(outcomes))
    print(summary(outcomes))
    return 0 if all(o.result != "error" for o in outcomes) else 1
