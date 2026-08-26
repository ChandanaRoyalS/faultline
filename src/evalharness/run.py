"""One scored run, as one command (T4.1, ADR-0022 §3).

    uv run python -m evalharness.run cart-dependency-latency

The protocol, in order: **baseline gate**, inject, wait for the orchestrator to correlate,
invoke `faultline-investigate` as the CLI it is, revert, confirm recovery, score. One driver of
the world throughout, enforced by a lock.

**`faultline-investigate` is invoked as a subprocess, not imported.** ADR-0004 keeps benchmark
infrastructure out of the product and ADR-0009 specifies the harness works "through public
interfaces only". Importing the runner would make the harness a second caller of internals that
the CLI's exit codes and stdout already expose - and the exit code is the thing being relied on,
so it has to be the thing being exercised.

**A run that dies is a recorded discard, never a deletion.** ADR-0022 §3.3: if a run is
discarded, the run and the reason are recorded in the results directory. That rule was written
for holdout honesty and it costs nothing to apply everywhere, so it is applied everywhere: the
run directory is created before the gate is read, and whatever happens next is written into it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evalharness import gate
from evalharness.provenance import recorder_provenance
from evalharness.scoring import Categories, ScoredRun, score_label, score_triage

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = REPO_ROOT / "evals" / "runs"
LOCK_PATH = REPO_ROOT / ".faultline" / "harness.lock"

USD_PER_MTOK_IN = 5.0
USD_PER_MTOK_OUT = 25.0

CORRELATE_TIMEOUT_SECONDS = 900
CORRELATE_POLL_SECONDS = 20
SETTLE_AFTER_ALERT_SECONDS = 90
"""Once the first episodes land, wait this long before investigating.

Every smoke from T3.4 onward did the same by hand: the first alert opens the incident and the
rest of the blast radius arrives over the following minute or two, so investigating on the first
episode scores triage against an incident that is still filling up."""

RECOVERY_TIMEOUT_SECONDS = 420
RECOVERY_POLL_SECONDS = 30

TRANSIENT_SIGNALS: tuple[str, ...] = (
    "overloaded_error",
    "OverloadedError",
    "rate_limit_error",
    "RateLimitError",
    "Error code: 429",
    "Error code: 500",
    "Error code: 502",
    "Error code: 503",
    "Error code: 504",
    "Error code: 529",
    "APIConnectionError",
    "APITimeoutError",
)
"""Failures worth trying again: the provider was busy, not the request was wrong.

**A 400 is deliberately absent.** `invalid_request_error` covers a malformed request and an
exhausted credit balance, and both are terminal - T4.1's second run died on the latter and
retrying it would have burned three more world injections to learn the same thing.
"""

RETRY_DELAYS_SECONDS: tuple[int, ...] = (20, 60, 120)
"""Three attempts after the first, at widening delays. **Small and fixed, not adaptive.**

Sized against what a retry costs *here* rather than against a service-level objective. A retry is
cheap - the fault is still injected and the incident still exists, so only the investigation
repeats - while the alternative is what the first sweep paid: a 529 on the first model call cost
an injection, a correlation wait, a revert and ten minutes, for one scenario slot.

Widening because a provider that is busy now is often busy in twenty seconds; three because a
provider still refusing after three and a half minutes is having an outage, and a sweep should
report that rather than sit in it.
"""


class RunError(RuntimeError):
    """The run cannot continue. The reason is recorded as a discard before this escapes."""


class WorldLock:
    """One driver of the world. **Does not wait.**

    Waiting on a world lock is how two harness processes interleave injections with nothing in
    either log to show it. An instruction to a human since T3.3; a file since T4.1.
    """

    def __init__(self, path: Path = LOCK_PATH) -> None:
        self._path = path

    def __enter__(self) -> WorldLock:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise RunError(
                f"another harness run holds {self._path}: {self._path.read_text().strip()}. "
                "Nothing was injected. Delete the file if that process is gone."
            ) from None
        os.write(handle, f"pid {os.getpid()} since {datetime.now(UTC).isoformat()}\n".encode())
        os.close(handle)
        return self

    def __exit__(self, *exc: object) -> None:
        self._path.unlink(missing_ok=True)


class RunDir:
    """Where a run's artifacts land, and where its discard is recorded if it has one."""

    def __init__(self, run_id: str, root: Path = RUN_ROOT) -> None:
        self.run_id = run_id
        self.path = root / run_id
        self.path.mkdir(parents=True, exist_ok=True)
        self.manifest: dict[str, Any] = {"run_id": run_id}

    def write(self, name: str, content: str) -> Path:
        target = self.path / name
        target.write_text(content)
        return target

    def save_manifest(self) -> Path:
        return self.write("manifest.json", json.dumps(self.manifest, indent=2, default=str) + "\n")

    def discard(self, reason: str, detail: str = "") -> Path:
        """**Recorded, not deleted.** The directory stays and says why it is not a result."""
        self.manifest["discarded"] = {"reason": reason, "at": datetime.now(UTC).isoformat()}
        self.save_manifest()
        return self.write(
            "DISCARDED.md",
            f"# Discarded run\n\n**Reason:** {reason}\n\n"
            f"Recorded rather than deleted, per ADR-0022 §3.3: a discarded run and its reason "
            f"stay in the results directory, so the number of runs is a fact nobody can hide "
            f"by tidying.\n\n{detail}\n",
        )


def _sh(args: list[str], env: dict[str, str] | None = None, timeout: int = 1800) -> tuple[int, str]:
    merged = {**os.environ, **(env or {})}
    result = subprocess.run(
        args, capture_output=True, text=True, check=False, env=merged, timeout=timeout
    )
    return result.returncode, result.stdout + result.stderr


def open_incidents(dsn: str) -> list[str]:
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM incidents WHERE state NOT IN ('resolved', 'failed')")
        return [row[0] for row in cur.fetchall()]


def expected_episodes(bundle: dict[str, Any]) -> int:
    """How many episodes to wait for, read from the bundle rather than assumed.

    **The first sweep discarded a scenario over this.** `min_episodes` was hard-coded to 2, and
    `frauddetection-memory-squeeze` alerts on exactly one service - `frauddetectionservice`, and
    nothing downstream, because a sparse service failing quietly pages nobody else. It could
    never have satisfied the wait, so it timed out at 900s and was recorded as though the world
    had not reacted. The world reacted exactly as its bundle says it does.

    Two is still right where the blast radius is wider: it is the cheapest signal that the radius
    is filling rather than that one alert arrived early. So: two, or the whole radius if the
    radius is smaller than two.
    """
    services = {
        entry.get("service")
        for entry in bundle.get("alerts_over_window") or ()
        if entry.get("service")
    }
    return min(2, max(1, len(services)))


def wait_for_incident(dsn: str, after: datetime, min_episodes: int = 2) -> str:
    """Poll for an incident the orchestrator opened after the injection."""
    import psycopg

    deadline = time.monotonic() + CORRELATE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT i.id, count(e.*) FROM incidents i "
                "LEFT JOIN incident_episodes e ON e.incident_id = i.id "
                "WHERE i.state = 'triaging' AND i.opened_at >= %s GROUP BY i.id",
                (after,),
            )
            for incident_id, episodes in cur.fetchall():
                if episodes >= min_episodes:
                    print(f"  incident {incident_id} with {episodes} episode(s)")
                    return str(incident_id)
        time.sleep(CORRELATE_POLL_SECONDS)
    raise RunError(
        f"no incident reached {min_episodes} episode(s) within {CORRELATE_TIMEOUT_SECONDS}s. "
        "The fault may not alert on this world - check the bundle's alerts_over_window, and "
        "note that a sparse service can take far longer than a busy one to trip a rule "
        "(evals/scenarios/CATALOG.md)."
    )


def confirm_recovery() -> gate.GateReading:
    """The gate, run again after the revert. Same checks, so recovery means the same thing
    quiet meant."""
    deadline = time.monotonic() + RECOVERY_TIMEOUT_SECONDS
    reading = gate.read()
    while time.monotonic() < deadline and not reading.passed:
        time.sleep(RECOVERY_POLL_SECONDS)
        reading = gate.read()
    return reading


def bundle_for(scenario_id: str) -> dict[str, Any]:
    for split in ("dev", "holdout"):
        path = REPO_ROOT / "evals/scenarios/artifacts" / split / scenario_id / "manifest.json"
        if path.exists():
            return dict(json.loads(path.read_text()))
    raise RunError(f"no recorded bundle for {scenario_id}")


def read_trajectory_facts(dsn: str, trajectory_id: str) -> dict[str, Any]:
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*), coalesce(sum(tokens_in),0), coalesce(sum(tokens_out),0) "
            "FROM trajectory_steps WHERE trajectory_id = %s",
            (trajectory_id,),
        )
        steps, tin, tout = cur.fetchone() or (0, 0, 0)
        cur.execute(
            "SELECT model, runtime_version, budget_exhausted FROM trajectories WHERE id = %s",
            (trajectory_id,),
        )
        row = cur.fetchone() or ("", "", False)
    return {
        "steps": int(steps),
        "tokens_in": int(tin),
        "tokens_out": int(tout),
        "model": row[0],
        "runtime_version": row[1],
        "budget_exhausted": bool(row[2]),
    }


ZERO_STEP_DISCARD = (
    "the trajectory has no steps: nothing ran, so there is nothing to score. "
    "Rows like this exist from before T3.5's guard - `f7261a74-6c83-4070-a6d6-2b414d3929cb` "
    "is one, written by a run that raised ModuleNotFoundError before the first model call. "
    "An empty row is indistinguishable from an investigation that produced no evidence, so it "
    "is discarded explicitly rather than counted as either (ADR-0022 §4)."
)


def score(
    run_id: str,
    scenario_id: str,
    bundle: dict[str, Any],
    artifact: dict[str, Any],
    facts: dict[str, Any],
    models: dict[str, str],
) -> ScoredRun:
    """Everything deterministic, from the artifact the CLI wrote and the trajectory it named."""
    verdict = artifact.get("verdict") or {}
    flags = tuple(artifact.get("flags") or ())
    failed = tuple(f"{name}: {why}" for name, why in artifact.get("failed_dispatches") or ())
    contradictions = tuple(f for f in flags if f.startswith("contradiction:"))
    exhausted = next((f for f in flags if f.startswith("budget exhausted")), None)

    return ScoredRun(
        run_id=run_id,
        scenario_id=scenario_id,
        trajectory_id=artifact.get("trajectory_id"),
        triage=score_triage(
            predicted=set(artifact.get("blast_radius") or ()),
            alerts_over_window=list(bundle.get("alerts_over_window") or ()),
            unmeasured_edges=int(artifact.get("unmeasured_edges") or 0),
        ),
        fault_class=score_label(scenario_id, bundle["fault_class"], verdict.get("fault_class")),
        fix_class=score_label(
            scenario_id, bundle["expected_remediation_class"], verdict.get("remediation_class")
        ),
        categories=Categories(
            # Disjoint on purpose: a budget-exhaustion flag and a contradiction flag each have
            # their own category, so leaving them in `flagged` too would count one run twice in
            # a sweep's category totals. `flagged` is what is left over.
            flagged=tuple(f for f in flags if f not in contradictions and f != exhausted),
            failed_alone=failed,
            contradictions=contradictions,
            budget_exhausted_reason=exhausted,
            narrative_refused=artifact.get("narrative_error"),
        ),
        tokens_in=int(facts.get("tokens_in", 0)),
        tokens_out=int(facts.get("tokens_out", 0)),
        cost_usd=facts.get("tokens_in", 0) / 1e6 * USD_PER_MTOK_IN
        + facts.get("tokens_out", 0) / 1e6 * USD_PER_MTOK_OUT,
        models=models,
        runtime_version=str(facts.get("runtime_version") or ""),
    )


# --- the protocol ---------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="evalharness.run",
        description=(
            "One scored run: baseline gate, inject, correlate, investigate, revert, confirm, "
            "score (T4.1, ADR-0022 §3)."
        ),
        epilog=(
            "Exit codes: 0 the run completed and was scored; 3 the baseline gate refused and "
            "nothing was injected; 4 the run was discarded, and the reason is in the run "
            "directory's DISCARDED.md. A discarded run is never deleted."
        ),
    )
    p.add_argument("scenario_id")
    p.add_argument("--postgres-dsn", default=None)
    p.add_argument("--max-tool-calls", type=int, default=4)
    p.add_argument(
        "--max-tool-calls-changes",
        type=int,
        default=None,
        metavar="N",
        help="override the changes specialist's bound only (T4.7)",
    )
    p.add_argument("--max-tokens", type=int, default=120_000)
    p.add_argument(
        "--holdout",
        action="store_true",
        help="permit a holdout scenario. Refused without it, because a holdout run is a "
        "different experiment and should be hard to start by accident (ADR-0008 axis 1)",
    )
    return p


DID_NOT_START = "did not start"
"""The runner's own marker for a failure before the first trajectory step (T3.5).

**Only a failed start is retryable, and that is not a policy choice - it is what the state
machine already says.** A run that got somewhere and then failed leaves the incident `FAILED`,
which ADR-0016 makes terminal, so `faultline-investigate` correctly refuses it on the next
attempt: the retry can only ever exit 3. A failed start leaves the incident in `triaging`,
untouched and investigable, which is exactly the case retry was built for.

Measured, not reasoned: T4.5's sweep lost **two** scenarios this way before the distinction was
drawn. Both took a 529 partway through an investigation, marked the incident `FAILED`, and then
spent a retry being told the incident was terminal.
"""


def transient_signal(transcript: str) -> str | None:
    """The transient failure worth trying again, or `None`.

    Two conditions, both required: the provider failed transiently **and** the run had not yet
    touched the incident. See `DID_NOT_START`.
    """
    if DID_NOT_START not in transcript:
        return None
    return next((signal for signal in TRANSIENT_SIGNALS if signal in transcript), None)


def _investigate(incident_id: str, scenario_id: str, out: Path, args: Any) -> tuple[int, str]:
    """`faultline-investigate`, as a subprocess. **Its exit code is the contract being used.**"""
    cmd = [
        "faultline-investigate",
        incident_id,
        "--exclude-origin",
        scenario_id,
        "--out",
        str(out),
        "--max-tool-calls",
        str(args.max_tool_calls),
        "--max-tokens",
        str(args.max_tokens),
    ]
    if args.max_tool_calls_changes:
        cmd += ["--max-tool-calls-changes", str(args.max_tool_calls_changes)]
    if args.postgres_dsn:
        cmd += ["--postgres-dsn", args.postgres_dsn]
    print(f"  $ {' '.join(cmd)}")
    return _sh(cmd)


def _investigate_with_retry(
    incident_id: str, scenario_id: str, out: Path, args: Any
) -> tuple[int, str, list[dict[str, Any]]]:
    """The investigation, retried on transient provider failures only.

    **The world stays as it is between attempts.** The fault is still injected and the incident
    still exists, so a retry repeats the investigation and nothing else - which is what makes
    retrying cheap enough to be worth doing at all.

    Every attempt is recorded, including the successful one, so a scored run says how many it
    needed rather than only whether it eventually worked. A run that exhausts the delays fails
    exactly as it does today: no verdict artifact, and the run is discarded with its reason.
    """
    attempts: list[dict[str, Any]] = []
    transcript = ""
    code = 1
    for attempt, delay in enumerate([0, *RETRY_DELAYS_SECONDS], start=1):
        if delay:
            print(f"  transient failure; waiting {delay}s before attempt {attempt}")
            time.sleep(delay)
        code, transcript = _investigate(incident_id, scenario_id, out, args)
        signal = transient_signal(transcript) if code != 0 else None
        attempts.append(
            {
                "attempt": attempt,
                "waited_seconds": delay,
                "exit_code": code,
                "transient_signal": signal,
            }
        )
        if code == 0 or signal is None:
            # Either it worked, or it failed for a reason repeating will not change.
            break
    return code, transcript, attempts


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    from faultline.agents.settings import AgentSettings
    from faultline.context.settings import ContextSettings

    dsn = args.postgres_dsn or ContextSettings().postgres_dsn
    settings = AgentSettings()

    bundle = bundle_for(args.scenario_id)
    if bundle.get("split") == "holdout" and not args.holdout:
        print(f"REFUSED: {args.scenario_id} is a holdout scenario; pass --holdout to mean it")
        return 3
    if not bundle.get("alerts_over_window"):
        print(
            f"REFUSED: {args.scenario_id} has an empty alerts_over_window and cannot produce "
            "an incident, so it cannot be investigated. Two dev bundles are in this state "
            "(currency-cpu-throttle, flag-service-crashloop) and both carry an INVALID.md."
        )
        return 3

    started = datetime.now(UTC)
    run = RunDir(f"{started:%Y%m%dT%H%M%SZ}-{args.scenario_id}")
    run.manifest.update(
        {
            "scenario_id": args.scenario_id,
            "split": bundle.get("split"),
            "scenario_fingerprint": bundle.get("scenario_fingerprint"),
            "started_at": started.isoformat(),
            "recorder": recorder_provenance("evalharness.run", REPO_ROOT),
            "models": settings.effective_models(
                ["planner", "metrics", "logs", "changes", "traces", "synthesizer", "scribe"]
            ),
            "efforts": {"default": settings.effort, **settings.role_efforts},
            # All four bounds, not the two the CLI happens to take. **Budget bounds are
            # experiment parameters the stamp does not cover** (T4.7): two runs with the same
            # stamp and different bounds are different experiments, so the bounds have to be
            # recorded in full and printed beside the stamp wherever a figure appears.
            "budget": {
                "max_tool_calls_per_specialist": args.max_tool_calls,
                "per_specialist_tool_calls": (
                    {"changes": args.max_tool_calls_changes} if args.max_tool_calls_changes else {}
                ),
                "max_tokens": args.max_tokens,
                "wall_clock_seconds": settings.budget_wall_clock_seconds,
                "max_dispatch_rounds": settings.budget_max_dispatch_rounds,
            },
        }
    )
    print(f"run {run.run_id}")

    try:
        with WorldLock():
            print("baseline gate...")
            reading = gate.require(open_incidents(dsn))
            run.manifest["baseline_gate"] = reading.as_dict()
            print(f"  clean: {reading.services_reporting} services reporting, 0 alerts")

            print(f"injecting {args.scenario_id}...")
            injected_at = datetime.now(UTC)
            code, out = _sh(["faultline-inject", "start", args.scenario_id])
            run.manifest["injected_at"] = injected_at.isoformat()
            run.write("inject.txt", out)
            if code != 0:
                raise RunError(f"injection failed:\n{out}")

            try:
                print("waiting for the orchestrator to correlate...")
                incident_id = wait_for_incident(dsn, injected_at, expected_episodes(bundle))
                run.manifest["incident_id"] = incident_id
                print(f"  settling {SETTLE_AFTER_ALERT_SECONDS}s so the blast radius fills")
                time.sleep(SETTLE_AFTER_ALERT_SECONDS)

                print("investigating...")
                code, transcript, attempts = _investigate_with_retry(
                    incident_id, args.scenario_id, run.path, args
                )
                run.write("investigate.txt", transcript)
                run.manifest["investigate_exit_code"] = code
                run.manifest["investigate_attempts"] = attempts
                print(transcript)
            finally:
                print("reverting...")
                _, revert = _sh(["faultline-inject", "stop", args.scenario_id])
                run.manifest["reverted_at"] = datetime.now(UTC).isoformat()
                run.write("revert.txt", revert)

            print("confirming recovery...")
            recovery = confirm_recovery()
            run.manifest["recovery"] = recovery.as_dict()
            if not recovery.passed:
                print(f"  WARNING: world not quiet after revert: {recovery.refusals}")

        artifact_path = run.path / f"{incident_id}-verdict.json"
        if not artifact_path.exists():
            raise RunError(
                f"the investigation wrote no verdict artifact (exit {code}). "
                f"Its transcript is in {run.path / 'investigate.txt'}."
            )
        artifact = json.loads(artifact_path.read_text())
        trajectory_id = artifact.get("trajectory_id")
        facts = read_trajectory_facts(dsn, trajectory_id) if trajectory_id else {"steps": 0}
        if facts["steps"] == 0:
            raise RunError(ZERO_STEP_DISCARD)

        scored = score(
            run.run_id, args.scenario_id, bundle, artifact, facts, run.manifest["models"]
        )
        scored.budget = dict(run.manifest["budget"])
        run.manifest["score"] = scored.as_dict()
        run.manifest["finished_at"] = datetime.now(UTC).isoformat()
        run.save_manifest()
        report = scored.report()
        run.write("report.txt", report + "\n")
        print("\n" + report)
        print(f"\nartifacts under {run.path}")
        return 0

    except gate.GateRefusedError as refused:
        run.manifest["baseline_gate"] = gate.read().as_dict()
        run.discard("baseline gate refused", str(refused))
        print(f"REFUSED: {refused}")
        return 3
    except (RunError, subprocess.TimeoutExpired) as failure:
        run.discard("run failed", str(failure))
        print(f"DISCARDED: {failure}")
        print(f"recorded, not deleted: {run.path / 'DISCARDED.md'}")
        return 4


def run_cli() -> None:  # pragma: no cover - console entry point
    sys.exit(main())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
