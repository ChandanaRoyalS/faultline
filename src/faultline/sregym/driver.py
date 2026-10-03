"""One SREGym attempt, end to end: `faultline-sregym` (T7.2, ADR-0044).

SREGym's agent row runs this inside its agent container, after `install-faultline.sh`. In order:

1. wait for the conductor to reach the diagnosis stage, as every SREGym driver does;
2. read `/get_app`: the application and its namespace, and nothing else, because that is what
   SREGym gives every agent;
3. open the CONNECT tunnel to the benchmark database, and **recreate this attempt's database from
   the seeded template**, so nothing one attempt wrote is visible to the next (the run's
   constraint 5);
4. open the incident on the standard alarms (`faultline.sregym.opening`) and store it;
5. run `faultline-investigate` **as the CLI it is**, with the scored runs' budget (`--max-tool-calls
   4 --max-tokens 120000`), notifications off, and `FAULTLINE_TOOLS_BACKEND=sregym`;
6. read the verdict and the bound evidence back, render them as frozen, and POST the text to
   `/submit` for the diagnosis stage;
7. write what happened to `/logs/faultline/attempt.json`.

**What never reaches the model**: SREGym's problem identity (it withholds `SREGYM_PROBLEM_ID`, and
`SREGYM_ARTIFACT_ID` is a random token used only to name this attempt's files), and anything of
SREGym's source, oracles or checklist.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from faultline.sregym.mcp import McpClient
from faultline.sregym.opening import Opener
from faultline.sregym.profiles import profile_for
from faultline.sregym.render import NO_VERDICT, render
from faultline.sregym.toolset import NAMESPACE_VAR, SESSION_VAR
from faultline.sregym.tunnel import Tunnel

TEMPLATE_DATABASE = "faultline_seeded"
"""Migrated and seeded once per run, at the run's commit, by the pilot's registered operation."""

ATTEMPT_DATABASE = "faultline"

INVESTIGATE_ARGS = ("--max-tool-calls", "4", "--max-tokens", "120000", "--no-notify")
"""The scored runs' budget (`evalharness.run`'s defaults) and no notification: a benchmark is not
an incident lifecycle."""

READY_STAGES = frozenset({"diagnosis", "mitigation"})

INVESTIGATE_TIMEOUT_SECONDS = 1500
"""Below SREGym's 1,800 s agent timeout, which also covers the install and the opening's up to five
minutes. The investigation's own wall clock (600 s, `AgentSettings`) normally ends it far sooner;
this bound is for a hang, after which the attempt still submits `NO_VERDICT` before SREGym kills
the container."""


def api_base() -> str:
    return (
        f"http://{os.environ.get('API_HOSTNAME', 'localhost')}:{os.environ.get('API_PORT', '8000')}"
    )


def _get(path: str) -> Any:
    with urllib.request.urlopen(f"{api_base()}{path}", timeout=60) as reply:
        return json.loads(reply.read())


def _post(path: str, body: dict[str, Any]) -> Any:
    request = urllib.request.Request(
        f"{api_base()}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as reply:
        return json.loads(reply.read() or b"null")


def wait_until_ready(timeout: float = 300.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            stage = str(_get("/status").get("stage"))
            if stage in READY_STAGES:
                return stage
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError(f"the conductor did not reach {sorted(READY_STAGES)} in {timeout:.0f} s")


def reset_database(admin_dsn: str) -> None:
    """Drop this attempt's database and recreate it from the seeded template."""
    import psycopg

    with psycopg.connect(admin_dsn, autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{ATTEMPT_DATABASE}" WITH (FORCE)')
        connection.execute(f'CREATE DATABASE "{ATTEMPT_DATABASE}" TEMPLATE "{TEMPLATE_DATABASE}"')


def bound_evidence(dsn: str, trajectory_id: str) -> list[Any]:
    """The `Evidence` the specialists' completions bound and stored (T3.6), from the trajectory."""
    import psycopg

    from faultline.agents.evidence import Evidence
    from faultline.agents.trajectory import PostgresTrajectoryStore, StepKind

    trajectory = PostgresTrajectoryStore(psycopg.connect(dsn)).get(trajectory_id)
    if trajectory is None:
        return []
    items: list[Any] = []
    for step in trajectory.steps:
        if step.kind is StepKind.COMPLETION:
            for raw in step.payload.get("evidence") or []:
                items.append(Evidence.model_validate(raw))
    return items


@dataclass
class Attempt:
    """What `/logs/faultline/attempt.json` records."""

    started_at: str
    app_name: str = ""
    namespace: str = ""
    application: str = ""
    evaluations: int = 0
    fallback: bool = False
    episodes: list[dict[str, str]] = field(default_factory=list)
    opening_errors: list[str] = field(default_factory=list)
    incident_id: str = ""
    investigate_exit: int | None = None
    trajectory_id: str = ""
    verdict: bool = False
    evidence_cited: int = 0
    submission: str = ""
    submitted: Any = None
    error: str = ""
    ended_at: str = ""


def run(out: Path) -> Attempt:
    attempt = Attempt(started_at=datetime.now(UTC).isoformat())
    out.mkdir(parents=True, exist_ok=True)
    tunnel: Tunnel | None = None
    submission = NO_VERDICT
    try:
        wait_until_ready()
        app = _get("/get_app")
        attempt.app_name = str(app.get("app_name") or "")
        attempt.namespace = str(app.get("namespace") or "")
        profile = profile_for(attempt.app_name)
        attempt.application = profile.application

        tunnel = Tunnel(
            os.environ.get("FAULTLINE_SREGYM_DB_HOST", "host.docker.internal"),
            int(os.environ.get("FAULTLINE_SREGYM_DB_PORT", "55432")),
        ).start()
        password = os.environ["FAULTLINE_SREGYM_DB_PASSWORD"]
        base = (
            f"host=127.0.0.1 port={tunnel.port} user=postgres password={password} sslmode=disable"
        )
        reset_database(f"{base} dbname=postgres")
        dsn = f"{base} dbname={ATTEMPT_DATABASE}"

        session = uuid.uuid4().hex
        client = McpClient(os.environ["MCP_SERVER_URL"], session_id=session)
        opener = Opener(client, profile, attempt.namespace)
        incident = opener.open()
        attempt.evaluations = opener.evaluations
        attempt.fallback = opener.fallback
        attempt.opening_errors = opener.errors
        attempt.episodes = [
            {"alertname": e.alertname or "", "service": e.service or "", "severity": e.severity}
            for e in incident.episodes.values()
        ]

        import psycopg

        from faultline.orchestrator.store import PostgresIncidentStore

        PostgresIncidentStore(psycopg.connect(dsn)).save(incident)
        attempt.incident_id = incident.id

        env = {
            **os.environ,
            "FAULTLINE_TOOLS_BACKEND": "sregym",
            "FAULTLINE_TOOLS_WORLD": "v2",
            "FAULTLINE_CONTEXT_APPLICATION": profile.application,
            "FAULTLINE_CONTEXT_POSTGRES_DSN": dsn,
            NAMESPACE_VAR: attempt.namespace,
            SESSION_VAR: session,
        }
        verdicts = out / "investigation"
        try:
            done = subprocess.run(
                ["faultline-investigate", incident.id, "--out", str(verdicts), *INVESTIGATE_ARGS],
                env=env,
                capture_output=True,
                text=True,
                timeout=INVESTIGATE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as expired:
            (out / "investigate.log").write_text(str(expired.stdout or ""))
            raise
        (out / "investigate.log").write_text(done.stdout + "\n--- stderr ---\n" + done.stderr)
        attempt.investigate_exit = done.returncode

        verdict_file = verdicts / f"{incident.id}-verdict.json"
        if verdict_file.exists():
            from faultline.agents.contracts import Verdict

            stored = json.loads(verdict_file.read_text())
            attempt.trajectory_id = str(stored.get("trajectory_id") or "")
            if stored.get("verdict"):
                verdict = Verdict.model_validate(stored["verdict"])
                evidence = bound_evidence(dsn, attempt.trajectory_id)
                submission = render(verdict, evidence)
                attempt.verdict = True
                attempt.evidence_cited = len(set(verdict.evidence))
    except Exception as exc:
        attempt.error = f"{type(exc).__name__}: {exc}"
    finally:
        if tunnel is not None:
            tunnel.stop()

    attempt.submission = submission
    try:
        attempt.submitted = _post("/submit", {"solution": submission, "stage": "diagnosis"})
    except Exception as exc:
        attempt.error = (attempt.error + "; " if attempt.error else "") + f"submit: {exc}"
    attempt.ended_at = datetime.now(UTC).isoformat()
    (out / "attempt.json").write_text(json.dumps(asdict(attempt), indent=2, default=str) + "\n")
    return attempt


def main() -> int:
    out = Path(os.environ.get("AGENT_LOGS_DIR", "/logs")) / "faultline"
    attempt = run(out)
    print(json.dumps({k: v for k, v in asdict(attempt).items() if k != "submission"}, default=str))
    return 0 if attempt.verdict and not attempt.error else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
