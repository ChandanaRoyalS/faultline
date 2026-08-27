"""`make demo` - one scripted run of the whole system, narrated for someone watching.

This is a **wrapper, not a second pipeline**. It shells out to the same `faultline-eval` the
sweeps use, so the demo run passes the same baseline gate, reverts the same way, confirms the
same recovery, and lands in `evals/runs/` like any other run. What it adds is narration: the
harness's own output is a progress log for someone who already knows the protocol, and this
turns it into a story for someone who does not.

Two things it deliberately does not do. It does not reimplement any step - a demo that drifts
from the real path is a demo of something else. And it does not touch product code, so the
pipeline stamp is identical to the one every published figure was measured under.

The scenario is fixed rather than chosen at runtime: see `SCENARIO` for why.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from evalharness.run import EVENT_PREFIX

REPO_ROOT = Path(__file__).resolve().parents[2]
KEY_PATH = Path.home() / ".faultline-anthropic-key"

CHANGES_BOUND = 8
"""The `changes` bound every claim about this scenario was measured under (T4.7).

The default is 4, and running the demo on the default was a mistake made once and caught by
running it: the planner asked for five `changes` dispatches, exhausted the bound at 4 of 4,
never reached the failing service's change history, and abstained - on the scenario this
repository has watched answer correctly six times out of six. T4.7 measured that starvation
and raised the bound; a new entry point that did not inherit the configuration reproduced it
exactly.

**A demo must run the configuration its claim rests on.** Choosing a scenario on evidence
gathered at one budget and then demonstrating it at another is a different experiment wearing
the first one's reputation.
"""

SCENARIO = "cart-redis-misconfig"
"""The most watchable scenario in the dev split, and the best-evidenced.

The criterion is a story a stranger can follow, and this one has all three parts. **A visible
symptom**: seven services alert, so the opening looks like the platform-wide event a real
responder fears. **A clean localization arc**: the blast radius narrows to one hop, cart, and
the alerting service turns out not to be the broken one - which is the single most useful
thing this system does and is invisible on a scenario where they coincide. **Decisive
evidence**: the answer is a change record naming the configuration that moved, so the finish
is a fact rather than an inference.

It is also the scenario this repository knows best. T4.10 ran it five times under a fixed
configuration and got the same correct verdict every time, six for six counting a prior
byte-identical row (`evals/runs/VARIANCE-2026-08-27.md`). "The demo always works" is a
project rule, and picking the one scenario whose repeat behaviour has actually been measured
is how that rule gets kept rather than hoped for.
"""


class DemoRefusedError(RuntimeError):
    """A precondition is missing. Nothing was injected and nothing was spent."""


def _say(line: str = "") -> None:
    print(line, flush=True)


def _beat(line: str) -> None:
    _say(f"\n  {line}")


def preflight() -> None:
    """Everything checked before a single dollar or container is touched."""
    if not KEY_PATH.is_file() and not os.environ.get("ANTHROPIC_API_KEY"):
        raise DemoRefusedError(
            f"no Anthropic credentials.\n"
            f"  The demo makes real model calls. Put a key in {KEY_PATH}\n"
            f"  (chmod 600), or export ANTHROPIC_API_KEY in your shell.\n"
            f"  Nothing else in this repository needs it - `make check` runs offline."
        )
    if shutil.which("faultline-eval") is None:
        raise DemoRefusedError(
            "faultline-eval is not on PATH.\n"
            "  Run `make install` first, or prefix the command with `uv run`."
        )
    # The agent runtime's model client is an optional extra (ADR-0020), lazily imported, so
    # a plain `uv sync` leaves it out and nothing notices until an investigation is already
    # mid-flight. Checked here because that is exactly what happened while building this
    # demo: an injected fault, a correlated incident, and a run discarded on an import error.
    try:
        import anthropic  # noqa: F401
    except ImportError:
        raise DemoRefusedError(
            "the agent runtime's model client is not installed.\n"
            "  Run `uv sync --extra agents`. It is optional because `make check`\n"
            "  never calls a model, so a plain `uv sync` leaves it out."
        ) from None

    if shutil.which("docker") is None:
        raise DemoRefusedError("docker is not installed, and the demo needs the world running.")

    running = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, check=False
    )
    names = set(running.stdout.split())
    missing = {"frontend", "cart-service", "prometheus"} - names
    if missing:
        raise DemoRefusedError(
            f"the world is not up - missing {', '.join(sorted(missing))}.\n"
            f"  Start it with `make world-up`, wait about two minutes for the\n"
            f"  containers to settle, then run `make demo` again."
        )


def intro() -> None:
    _say("=" * 72)
    _say("FAULTLINE DEMO - one incident, start to finish")
    _say("=" * 72)
    _say()
    _say("You are about to watch nine agents investigate a failure that is about")
    _say("to be injected into a real running microservice deployment. Nothing here")
    _say("is replayed or scripted: the alerts, the queries and the verdict all")
    _say("happen live, and the whole thing takes roughly fifteen minutes.")
    _say()
    _say(f"The scenario is `{SCENARIO}`. The agents are not told which scenario")
    _say("it is, which service broke, or that anything was injected at all. They")
    _say("see what an on-call engineer sees: alerts, and four tools to ask with.")
    _say()
    _say(f"It runs with the `changes` bound at {CHANGES_BOUND}, which is the configuration")
    _say("every published figure for this scenario was measured under (T4.7).")
    _say()
    _say("Watch for one thing in particular. The service that alerts loudest is")
    _say("not the service that broke, and the interesting question is whether the")
    _say("agents work that out or chase the noise.")
    _say()


def narrate(event: dict[str, Any]) -> None:
    """One progress event, in plain language. Unknown events are ignored on purpose:
    the harness may grow phases this narration has no story for, and a demo that crashes
    on an unfamiliar event is worse than one that stays quiet about it."""
    kind = event.get("event")
    if kind == "run":
        _beat(f"Run {event['run_id']}")
        _say(f"  Scenario: {event.get('title') or event['scenario']}")
        _say(f"  Split: {event.get('split')} - a development scenario, never a holdout one.")
    elif kind == "gate":
        _beat("BASELINE GATE")
        _say(f"  {event['services']} services reporting, zero alerts firing.")
        _say("  The world is quiet. This matters: injecting into an already-sick")
        _say("  world would measure the sickness as well as the fault.")
    elif kind == "injected":
        _beat("INJECTING THE FAULT")
        _say("  Done. Somewhere in the deployment, one service has just been given")
        _say("  a configuration it cannot work with. No agent has been told.")
    elif kind == "correlated":
        _beat("THE ORCHESTRATOR CORRELATES")
        _say("  Alerts started arriving and were grouped into ONE incident:")
        _say(f"  {event['incident_id']}")
        _say("  Several services are alerting. They are one event, not several,")
        _say("  and deciding that is the orchestrator's whole job.")
    elif kind == "settling":
        _beat(f"SETTLING {event['seconds']}s")
        _say("  Waiting for the blast radius to fill in, so the agents see the")
        _say("  incident as a responder would - after it has spread, not mid-spread.")
    elif kind == "investigating":
        _beat("THE INVESTIGATION BEGINS")
        _say("  The planner now decides which specialists to send and what to ask")
        _say("  each one. It holds no tools itself. This is the slow part - the")
        _say("  agents are making real queries against Prometheus, Loki and Jaeger.")
    elif kind == "investigated":
        _beat("THE INVESTIGATION IS DONE")
        _say(f"  Exit code {event['exit_code']}, on attempt {event['attempts']}.")
    elif kind == "reverted":
        _beat("REVERTING")
        _say("  The fault is being removed. This happens whether the investigation")
        _say("  succeeded or failed - the world is left as it was found.")
    elif kind == "recovered":
        _beat("CONFIRMING RECOVERY")
        if event["passed"]:
            _say(f"  {event['services']} services reporting, zero alerts. The world is")
            _say("  quiet again, and confirmed so rather than assumed so.")
        else:
            _say(f"  NOT QUIET: {event['refusals']}")
            _say("  Recorded rather than hidden. The next run's gate will refuse.")


def dispatch_arc(dsn: str, trajectory_id: str) -> None:
    """The part of the story the harness does not print: what the planner actually decided."""
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT payload FROM trajectory_steps WHERE trajectory_id=%s "
            "AND kind='completion' AND payload ? 'plan' ORDER BY seq",
            (trajectory_id,),
        )
        plans = [row[0]["plan"] for row in cur.fetchall()]
        cur.execute(
            "SELECT tool, request FROM trajectory_tool_calls WHERE trajectory_id=%s ORDER BY seq",
            (trajectory_id,),
        )
        calls = cur.fetchall()

    _beat("WHAT THE PLANNER DECIDED")
    for number, plan in enumerate(plans, 1):
        dispatches = plan.get("dispatches") or []
        _say(f"  Round {number}: {len(dispatches)} dispatches")
        for dispatch in dispatches:
            _say(f"    - {dispatch['specialist']:8} at {dispatch['service']}")
        for skipped in plan.get("skipped") or []:
            reason = (skipped.get("reason") or "").split(".")[0]
            _say(f"    - skipped {skipped['specialist']}: {reason}")

    _beat("WHAT THE SPECIALISTS ASKED THE WORLD")
    for tool, request in calls:
        _say(f"    {tool:16} {request.get('service')}")
    _say(f"  {len(calls)} tool calls. Every result came back inside a trust envelope")
    _say("  the agents are told to treat as untrusted data, never as instructions.")


def verdict_story(run_dir: Path, incident_id: str) -> None:
    artifact = run_dir / f"{incident_id}-verdict.json"
    if not artifact.is_file():
        return
    verdict = json.loads(artifact.read_text()).get("verdict") or {}
    _beat("THE VERDICT")
    _say(f"  Fault class : {verdict.get('fault_class')}")
    _say(f"  Class of fix: {verdict.get('class_of_fix')}")
    _say(f"  Confidence  : {verdict.get('confidence')}")
    _say()
    for line in _wrap(str(verdict.get("root_cause", "")), 68):
        _say(f"  {line}")
    open_questions = verdict.get("open_questions") or []
    if open_questions:
        _say()
        _say("  What it says it does NOT know:")
        for question in open_questions[:3]:
            for line in _wrap(question, 66):
                _say(f"    {line}")


def _wrap(text: str, width: int) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width) or [""]


def outro(run_dir: Path, scored: dict[str, Any]) -> None:
    fault = scored.get("fault_class") or {}
    cost = scored.get("cost_usd") or 0.0
    _beat("WHAT JUST HAPPENED")
    truth, returned = fault.get("truth"), fault.get("returned")
    if fault.get("correct"):
        _say(f"  The agents returned `{returned}`, and the ground truth is `{truth}`.")
        _say("  They were never told either.")
    elif fault.get("abstained"):
        _say(f"  The agents declined to name a class. The truth was `{truth}`.")
        _say("  An abstention is a result here, not a failure: this system is")
        _say("  built to say `unknown` rather than guess, and abstentions are")
        _say("  reported as coverage rather than hidden inside an accuracy figure.")
    else:
        _say(f"  The agents returned `{returned}`; the truth was `{truth}`. Wrong,")
        _say("  and recorded as wrong - see docs/RESULTS.md for the standing rate.")
    _say()
    _say(f"  This run cost ${cost:.4f} and is recorded in full at:")
    _say(f"    {run_dir}")
    _say()
    _say("  It is marked `demo` in its manifest, so no sweep aggregate will ever")
    _say("  count it. A run made to be watched is not a sample.")
    _say()
    _say("  The measured numbers - accuracy, coverage, variance, and what is still")
    _say("  unknown - are in docs/RESULTS.md. Every figure there carries its n.")
    _say("=" * 72)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="faultline-demo", description=__doc__)
    ap.add_argument("--scenario", default=SCENARIO, help=f"default: {SCENARIO}")
    args = ap.parse_args(argv)

    try:
        preflight()
    except DemoRefusedError as refused:
        _say(f"\nCannot run the demo: {refused}\n")
        return 3

    env = dict(os.environ)
    if "ANTHROPIC_API_KEY" not in env and KEY_PATH.is_file():
        env["ANTHROPIC_API_KEY"] = KEY_PATH.read_text().strip()

    intro()

    proc = subprocess.Popen(
        [
            "faultline-eval",
            args.scenario,
            "--max-tool-calls-changes",
            str(CHANGES_BOUND),
            "--demo",
            "--progress-json",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        cwd=REPO_ROOT,
    )
    events: dict[str, dict[str, Any]] = {}
    assert proc.stdout is not None
    for line in proc.stdout:
        if not line.startswith(EVENT_PREFIX):
            continue
        event = json.loads(line[len(EVENT_PREFIX) :])
        events[str(event["event"])] = event
        narrate(event)
    code = proc.wait()

    scored = events.get("scored")
    if scored is None:
        _say("\n  The run did not reach a verdict. Its directory records why -")
        _say("  a discarded run is never deleted.")
        return code or 4

    run_dir = Path(scored["run_dir"])
    from faultline.context.settings import ContextSettings

    if scored.get("trajectory_id"):
        dispatch_arc(ContextSettings().postgres_dsn, scored["trajectory_id"])
    correlated = events.get("correlated")
    if correlated:
        verdict_story(run_dir, correlated["incident_id"])

    narrative = next(run_dir.glob("*-narrative.md"), None)
    if narrative:
        _beat("THE NARRATIVE THE SCRIBE WROTE")
        _say("  Written for a human reader, and checked by a leak guard that")
        _say("  refuses to render it if it names the injector or a fault class.")
        _say()
        for line in narrative.read_text().splitlines():
            _say(f"  {line}")

    outro(run_dir, scored)
    return code


def run_cli() -> None:  # pragma: no cover - console entry point
    sys.exit(main())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
