"""`faultline-batch` - the headline run and T7.3's batch, one slot at a time, on the Mac.

Built as the headline run's Addendum 1, items 8 and 9 register it
(`evals/runs/PREREGISTRATION-headline-v2.md`), and shared with T7.3's batch
(`PREREGISTRATION-T7.3.md`, Addendum 1, *The randomized queue*):

- **one slot at a time from a fixed queue**, which `faultline-batch queue` prints from a seed and
  which is committed before the batch starts. Nothing in it changes after a result;
- **the world check before every slot** (`scripts/world_check.py`). On a quote-clock failure the
  batch restarts quote and checks again (Q121, the owner's decision of 2026-10-04);
- **the corpus and both stamps checked before every slot**: the corpus is frozen at the pins in
  `generations` (item 8), and a stamp that differs invalidates the run (*The setup, frozen*);
- **the tally after every slot by the registered rule** (*The budget, as a hard stop*), and **the
  stop** when it passes the registered line.

## Why not `faultline-sweep`

The sweep runs one configuration over a catalog. A queue slot is a scenario **and an arm**, and
each arm is a different `faultline-eval` invocation: a `--baseline` flag for B0-B2 and E1, an
environment switch for E2-E9 (T7.3's Addendum 1). The sweep's ceiling also prices every token at
the agent's $5/$25 with no correction, which is not the registered tally. What the sweep already
gets right is reused rather than restated: its exit-code names, which codes mean *nothing was
injected*, its settle window and its retry wait.

## The tally, exactly as registered

*"Tallied after every run from recorded tokens at the published prices: agent and baseline tokens
x 1.26 (T7.2's correction); each judge call from its own tokens; each pre-flight probe at its
token."* So, per run directory carrying the batch's label:

- the trajectory store's tokens **by role**, each role priced at the model the run used for it
  (the manifest's `models`, then its `ablation_config.role_models`, then the default model), the
  sum multiplied by `BILLED_FACTOR`;
- the judge's recorded tokens at the judge model's price, uncorrected;
- one probe per launch that probes, at `preflight.PROBE_TOKENS`.

An unknown model is refused rather than priced at a guess (`judge.JudgeSettings.usd_per_mtok`
says why). **The owner's console reading is the authority**; this is the stop line's reading.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evalharness.sweep import CLEARABLE, EXIT_NAMES, RETRY_WAIT_SECONDS, SETTLE_SECONDS

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = REPO_ROOT / "evals" / "runs"
WORLD_CHECK = REPO_ROOT / "scripts" / "world_check.py"
T73_SCENARIOS = REPO_ROOT / "docs" / "evidence" / "t7.3" / "scenarios.tsv"

REGISTERED_RUNTIME = "faultline/0.0.1+prompts:9ce16b66bbcc"
REGISTERED_CAPABILITY = "cap:91279a09"
"""Both registrations freeze these. **A stamp that differs at run time invalidates the run until
the registration is amended**, so the batch refuses the slot instead of running it."""

BILLED_FACTOR = 1.26
"""T7.2's console reading: 216 model calls billed against 156 persisted, so recorded trajectory
tokens under-count the bill by this factor (`evals/attempts/T7.2-run/RESULT.md`)."""

USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
"""Published prices, in and out, for the models the two registrations name: Faultline's and the
baselines' (`claude-opus-5`, `AgentSettings.usd_per_mtok_*`), E4's specialists
(`claude-sonnet-4-6`) and the judge (`claude-haiku-4-5`)."""

JUDGE_MODEL = "claude-haiku-4-5"
JUDGE_ENV = {"FAULTLINE_JUDGE_MODEL": JUDGE_MODEL, "FAULTLINE_JUDGE_ALLOW_SHARED_LINEAGE": "1"}
"""*The judge: `faultline-judge` on the agent arm's narratives, on `claude-haiku-4-5` with
`FAULTLINE_JUDGE_ALLOW_SHARED_LINEAGE=1`* (the headline registration). Not a headline axis; run
after each scored F slot so its spend is in the tally when the next slot is decided."""

PROBE_INPUT_TOKENS = 16
"""The pre-flight probe's prompt, rounded up. Its output is `preflight.PROBE_TOKENS`."""

QUOTE_RECHECKS = 17
"""After a quote restart, how many one-minute rechecks. The clock check reads the last 15 minutes
of quote spans, so the drifted ones leave its window only after 15 minutes."""

WORLD_RECHECKS = 5
"""For any other world-check failure (an alert still firing after the settle, say), how many
one-minute rechecks before the batch stops and names the slot. Not tuned: it mirrors the sweep's
retry wait, and a world that has not settled in five more minutes is a stop, not a slot."""

SPECIALISTS = ("metrics", "logs", "changes", "traces")
WEEK_SECONDS = str(7 * 24 * 3600)

SWITCH_ENV = (
    "FAULTLINE_CONTEXT_HOP_RADIUS",
    "FAULTLINE_CONTEXT_RETRIEVAL_MODE",
    "FAULTLINE_CONTEXT_RERANK_MODEL",
    "FAULTLINE_CONTEXT_RERANK_CANDIDATES",
    "FAULTLINE_CONTEXT_RERANK_REVISION",
    "FAULTLINE_AGENT_EVIDENCE_MODE",
    "FAULTLINE_AGENT_ROLE_MODELS",
    "FAULTLINE_AGENT_NO_CORPUS",
    "FAULTLINE_AGENT_BRIEFING_MODE",
    "FAULTLINE_AGENT_BUDGET_BRIEFING_TOKENS",
    "FAULTLINE_TOOLS_DEFAULT_LOOKBACK_SECONDS",
    "FAULTLINE_TOOLS_CHANGE_LOOKBACK_SECONDS",
    "FAULTLINE_TOOLS_MAX_WINDOW_SECONDS",
)
"""Every switch E2-E9 reads. **Stripped from the inherited environment before each slot**, so a
switch exported in the operator's shell can never leak into F or into another arm."""

HEADLINE_ARMS = ("F", "B0", "B1", "B2")
T73_CONFIGS = ("F", "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")


@dataclass(frozen=True)
class Arm:
    flags: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)


def judged(queue_kind: str, arm: str) -> bool:
    """Only the headline's F is judged: *`faultline-judge` on the agent arm's narratives*. T7.3's
    registration names no judge."""
    return queue_kind == "headline" and arm == "F"


def arms(rerank_revision: str | None = None) -> dict[str, Arm]:
    """Every arm of both registrations. E7's revision comes from the committed queue's header."""
    sonnet = json.dumps({name: "claude-sonnet-4-6" for name in SPECIALISTS}, sort_keys=True)
    rerank = {"FAULTLINE_CONTEXT_RERANK_MODEL": "cross-encoder/ms-marco-MiniLM-L-6-v2"}
    if rerank_revision:
        rerank["FAULTLINE_CONTEXT_RERANK_REVISION"] = rerank_revision
    return {
        "F": Arm(),
        "B0": Arm(flags=("--baseline", "b0")),
        "B1": Arm(flags=("--baseline", "b1")),
        "B2": Arm(flags=("--baseline", "b2")),
        "E1": Arm(flags=("--baseline", "b1")),
        "E2": Arm(env={"FAULTLINE_CONTEXT_HOP_RADIUS": "99"}),
        "E3": Arm(env={"FAULTLINE_AGENT_EVIDENCE_MODE": "raw"}),
        "E4": Arm(env={"FAULTLINE_AGENT_ROLE_MODELS": sonnet}),
        "E5": Arm(env={"FAULTLINE_AGENT_NO_CORPUS": "1"}),
        "E6": Arm(env={"FAULTLINE_CONTEXT_RETRIEVAL_MODE": "dense"}),
        "E7": Arm(env=rerank),
        "E8": Arm(
            env={
                "FAULTLINE_TOOLS_DEFAULT_LOOKBACK_SECONDS": WEEK_SECONDS,
                "FAULTLINE_TOOLS_CHANGE_LOOKBACK_SECONDS": WEEK_SECONDS,
                "FAULTLINE_TOOLS_MAX_WINDOW_SECONDS": WEEK_SECONDS,
            }
        ),
        "E9": Arm(env={"FAULTLINE_AGENT_BRIEFING_MODE": "push"}),
    }


# --- the queue ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Slot:
    slot: int
    pass_name: str
    scenario: str
    arm: str

    @property
    def holdout(self) -> bool:
        return self.pass_name == "holdout"


@dataclass
class Queue:
    kind: str
    seed: int
    slots: list[Slot]
    rerank_revision: str | None = None


def headline_queue(dev: Iterable[str], holdout: Iterable[str], seed: int) -> list[Slot]:
    """The headline's step 4: *dev pass then holdout pass, each scenario's four arms back to back
    in a rotating order, the scenario order shuffled by a seed fixed then.*

    One `random.Random(seed)` shuffles the sorted dev ids, then the sorted holdout ids. Within a
    pass, scenario *i*'s arms start at arm *i* mod 4, so no arm always runs first after a settle.
    """
    rng = random.Random(seed)
    slots: list[Slot] = []
    for pass_name, ids in (("dev", sorted(dev)), ("holdout", sorted(holdout))):
        order = list(ids)
        rng.shuffle(order)
        for index, scenario in enumerate(order):
            turn = index % len(HEADLINE_ARMS)
            for arm in HEADLINE_ARMS[turn:] + HEADLINE_ARMS[:turn]:
                slots.append(Slot(len(slots) + 1, pass_name, scenario, arm))
    return slots


def t73_queue(scenarios: Iterable[str], seed: int) -> list[Slot]:
    """T7.3's Addendum 1: *the 120 runs, 10 configurations x 12 scenarios, put in one order by
    `random.Random(seed)`*. One pass, so a discard's re-run goes at the end of the batch."""
    pairs = [(s, c) for s in sorted(scenarios) for c in T73_CONFIGS]
    random.Random(seed).shuffle(pairs)
    return [Slot(i, "t73", s, c) for i, (s, c) in enumerate(pairs, start=1)]


def t73_scenarios(path: Path = T73_SCENARIOS) -> list[str]:
    lines = path.read_text().splitlines()[1:]
    return [line.split("\t")[0] for line in lines if line.strip()]


def render_queue(queue: Queue) -> str:
    head = [f"# kind\t{queue.kind}", f"# seed\t{queue.seed}"]
    if queue.rerank_revision:
        head.append(f"# rerank_revision\t{queue.rerank_revision}")
    rows = [f"{s.slot}\t{s.pass_name}\t{s.scenario}\t{s.arm}" for s in queue.slots]
    return "\n".join([*head, "slot\tpass\tscenario\tarm", *rows]) + "\n"


def read_queue(text: str) -> Queue:
    meta: dict[str, str] = {}
    slots: list[Slot] = []
    for line in text.splitlines():
        if line.startswith("# "):
            key, _, value = line[2:].partition("\t")
            meta[key] = value
        elif line and not line.startswith("slot\t"):
            slot, pass_name, scenario, arm = line.split("\t")
            slots.append(Slot(int(slot), pass_name, scenario, arm))
    queue = Queue(meta["kind"], int(meta["seed"]), slots, meta.get("rerank_revision") or None)
    known = arms(queue.rerank_revision)
    for s in slots:
        if s.arm not in known:
            raise ValueError(f"slot {s.slot}: unknown arm {s.arm!r}")
        if s.arm == "E7" and not queue.rerank_revision:
            raise ValueError("the queue has E7 slots and no rerank_revision: E7 runs pinned")
    if [s.slot for s in slots] != list(range(1, len(slots) + 1)):
        raise ValueError("slots must be numbered 1..N in order")
    return queue


def slot_argv(slot: Slot, arm: Arm, label: str, remaining: int, total: int) -> list[str]:
    argv = ["faultline-eval", slot.scenario, "--runs-remaining", str(remaining), *arm.flags]
    if slot.holdout:
        argv.append("--holdout")
    pass_number = 2 if slot.holdout else 1
    return [
        *argv,
        "--sweep",
        label,
        "--sweep-slot",
        str(slot.slot),
        "--sweep-of",
        str(total),
        "--sweep-pass",
        str(pass_number),
    ]


def slot_env(base: Mapping[str, str], arm: Arm) -> dict[str, str]:
    env = {k: v for k, v in base.items() if k not in SWITCH_ENV}
    env.update(arm.env)
    return env


# --- the tally ------------------------------------------------------------------------------


def price(model: str, tokens_in: int, tokens_out: int) -> float:
    if model not in USD_PER_MTOK:
        raise ValueError(f"no published price recorded for {model!r}; add it before the run")
    usd_in, usd_out = USD_PER_MTOK[model]
    return tokens_in / 1e6 * usd_in + tokens_out / 1e6 * usd_out


def role_model(manifest: Mapping[str, Any], role: str, default_model: str) -> str:
    recorded = (manifest.get("models") or {}).get(role)
    if recorded:
        return str(recorded)
    tiers = (manifest.get("ablation_config") or {}).get("role_models") or {}
    return str(tiers.get(role) or default_model)


def run_usd(
    manifest: Mapping[str, Any], steps: Mapping[str, tuple[int, int]], default_model: str
) -> float:
    """One run directory's billed dollars: trajectory tokens by role x 1.26, plus its judge."""
    agent = sum(
        price(role_model(manifest, role, default_model), tin, tout)
        for role, (tin, tout) in steps.items()
    )
    judge = manifest.get("judge") or {}
    judged = price(
        str(judge.get("judge_model") or JUDGE_MODEL),
        int(judge.get("tokens_in") or 0),
        int(judge.get("tokens_out") or 0),
    )
    return agent * BILLED_FACTOR + judged


def probe_usd(probes: int, default_model: str) -> float:
    from evalharness.preflight import PROBE_TOKENS

    return probes * price(default_model, PROBE_INPUT_TOKENS, PROBE_TOKENS)


def steps_by_role(dsn: str, incident_id: str) -> dict[str, tuple[int, int]]:  # pragma: no cover
    import psycopg

    from faultline.pgread import reading

    with psycopg.connect(dsn) as conn, reading(conn) as cur:
        cur.execute(
            "SELECT s.role, COALESCE(SUM(s.tokens_in), 0), COALESCE(SUM(s.tokens_out), 0) "
            "FROM trajectory_steps s JOIN trajectories t ON t.id = s.trajectory_id "
            "WHERE t.incident_id = %s GROUP BY s.role",
            (incident_id,),
        )
        return {str(r): (int(i), int(o)) for r, i, o in cur.fetchall()}


@dataclass
class Tally:
    usd: float = 0.0
    runs: int = 0
    probes: int = 0

    def render(self) -> str:
        return f"${self.usd:.2f} over {self.runs} run dir(s) and {self.probes} probe(s)"


def tally(
    labels: Iterable[str],
    probes: int,
    default_model: str,
    steps: Callable[[str], Mapping[str, tuple[int, int]]],
    root: Path = RUN_ROOT,
) -> Tally:
    from evalharness.spend import manifests_of

    total = Tally(probes=probes)
    for label in labels:
        for manifest in manifests_of(label, root):
            total.runs += 1
            incident = manifest.get("incident_id")
            by_role = steps(str(incident)) if incident else {}
            total.usd += run_usd(manifest, by_role, default_model)
    total.usd += probe_usd(probes, default_model)
    return total


# --- the checks before a slot ---------------------------------------------------------------


def stamps() -> tuple[bool, str]:
    from evalharness.capability import capability_version
    from faultline.agents.stamp import runtime_version

    runtime, capability = runtime_version(), capability_version()
    ok = runtime == REGISTERED_RUNTIME and capability == REGISTERED_CAPABILITY
    return ok, f"{runtime} {capability}"


def corpus_frozen(state: Mapping[str, Any]) -> tuple[bool, str]:
    """The corpus of record, unchanged: both pins, and no holdout chunk (item 8)."""
    from evalharness.generations import CURRENT_CORPUS_BODY, CURRENT_CORPUS_SHAPE

    problems = []
    if state.get("sha256") != CURRENT_CORPUS_SHAPE:
        problems.append(f"shape {str(state.get('sha256'))[:12]} is not the pin")
    if state.get("body_sha256") != CURRENT_CORPUS_BODY:
        problems.append(f"body {str(state.get('body_sha256'))[:12]} is not the pin")
    if state.get("holdout_chunks"):
        problems.append(f"{state.get('holdout_chunks')} holdout chunk(s)")
    detail = f"{state.get('rows')} rows; " + ("; ".join(problems) or "at both pins")
    return not problems, detail


@dataclass
class WorldCheck:
    ok: bool
    output: str

    @property
    def quote_clock_failed(self) -> bool:
        return any(
            line.startswith("FAIL") and "quote's clock" in line for line in self.output.splitlines()
        )


def run_world_check() -> WorldCheck:  # pragma: no cover - the live world
    try:
        done = subprocess.run(
            [sys.executable, str(WORLD_CHECK)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return WorldCheck(False, "FAIL  the world check did not finish in 180 s")
    return WorldCheck(done.returncode == 0, done.stdout + done.stderr)


def restart_quote() -> None:  # pragma: no cover - the live world
    subprocess.run(["docker", "restart", "quote"], check=False, timeout=120)


def world_ready(
    check: Callable[[], WorldCheck],
    restart: Callable[[], None],
    wait: Callable[[float], None],
) -> tuple[bool, str]:
    """Q121's rule and the generic one: restart quote on a clock failure, then recheck."""
    result = check()
    if result.ok:
        return True, "world check passed"
    if result.quote_clock_failed:
        print("--- quote's clock failed the world check: restarting quote (Q121)", flush=True)
        restart()
        rechecks = QUOTE_RECHECKS
    else:
        rechecks = WORLD_RECHECKS
    for attempt in range(1, rechecks + 1):
        wait(RETRY_WAIT_SECONDS)
        result = check()
        if result.ok:
            return True, f"world check passed on recheck {attempt}"
    failed = [line for line in result.output.splitlines() if line.startswith("FAIL")]
    return False, "; ".join(failed) or result.output.strip()[-400:]


# --- the batch ------------------------------------------------------------------------------


@dataclass
class Row:
    slot: int
    pass_name: str
    scenario: str
    arm: str
    code: int
    attempts: int
    tally_usd: float
    rerun: bool = False

    @property
    def outcome(self) -> str:
        return str(EXIT_NAMES.get(self.code, f"exit {self.code}"))


@dataclass
class BatchResult:
    rows: list[Row] = field(default_factory=list)
    stopped: str | None = None
    unfinished: list[Slot] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    tally: Tally = field(default_factory=Tally)

    def render(self) -> list[str]:
        lines = ["", f"tally: {self.tally.render()}"]
        counts: dict[str, int] = {}
        for row in self.rows:
            counts[row.outcome] = counts.get(row.outcome, 0) + 1
        lines.append("outcomes: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        if self.removed:
            lines.append("removed after a second discard: " + ", ".join(self.removed))
        if self.stopped:
            lines.append(f"STOPPED: {self.stopped}")
        if self.unfinished:
            lines.append(f"unfinished: {len(self.unfinished)} slot(s)")
            lines += [f"  {s.slot} {s.pass_name} {s.scenario} {s.arm}" for s in self.unfinished]
        return lines


DISCARDS = frozenset({4, 6})
"""A discarded run and an INVALID one: each is *re-run once, at the end of its pass*."""


def run_batch(
    queue: Queue,
    *,
    label: str,
    stop_usd: float,
    also_count: Iterable[str] = (),
    from_slot: int = 1,
    to_slot: int | None = None,
    settle: int = SETTLE_SECONDS,
    retries: int = 6,
    launch: Callable[[list[str], dict[str, str]], int],
    judge: Callable[[str], None],
    find_run: Callable[[str, int], str | None],
    read_tally: Callable[[list[str], int], Tally],
    world: Callable[[], tuple[bool, str]],
    corpus: Callable[[], tuple[bool, str]],
    check_stamps: Callable[[], tuple[bool, str]] = stamps,
    wait: Callable[[float], None] = time.sleep,
    log: Callable[[Row], None] = lambda row: None,
    base_env: Mapping[str, str] | None = None,
    probes_before: int = 0,
) -> BatchResult:
    """The block `from_slot`..`to_slot` of the queue, then its discards once each.

    **`--runs-remaining` counts down over this block**, the horizon the harness's kafka headroom
    projection is told about. Over the whole queue (156 slots, about 54 hours at
    `gate.SWEEP_RUN_HOURS`) the projection refuses every slot; that is dev sweep 12's lesson, and
    how large a block may be is the operation addendum's to say.
    """
    known = arms(queue.rerank_revision)
    env0 = dict(os.environ if base_env is None else base_env)
    block = [s for s in queue.slots if from_slot <= s.slot <= (to_slot or len(queue.slots))]
    labels = [label, *also_count]
    result = BatchResult()
    probes = probes_before
    injected = False
    discarded: dict[str, list[Slot]] = {}
    second: set[tuple[str, str]] = set()

    def stop(reason: str, remaining: list[Slot]) -> BatchResult:
        result.stopped = reason
        pending = [s for waiting in discarded.values() for s in waiting if s not in remaining]
        result.unfinished = remaining + pending
        result.tally = read_tally(labels, probes)
        print(f"\n*** STOP: {reason}", flush=True)
        return result

    def run_one(slot: Slot, remaining: int, rerun: bool) -> str | None:
        nonlocal probes, injected
        result.tally = read_tally(labels, probes)
        if result.tally.usd > stop_usd:
            return (
                f"the tally passed the registered stop: {result.tally.render()} against "
                f"${stop_usd:.2f}. Stopped before slot {slot.slot}"
            )
        if injected and settle:
            print(f"--- settling {settle}s before slot {slot.slot}", flush=True)
            wait(settle)
        for name, check in (("stamps", check_stamps), ("corpus", corpus), ("world", world)):
            ok, detail = check()
            print(f"--- {name}: {detail}", flush=True)
            if not ok:
                return f"the {name} check failed before slot {slot.slot}: {detail}"
        arm = known[slot.arm]
        argv = slot_argv(slot, arm, label, remaining, len(queue.slots))
        env = slot_env(env0, arm)
        code, attempt = 0, 0
        for attempt in range(1, retries + 1):
            shown = " ".join(f"{k}={v}" for k, v in sorted(arm.env.items()))
            print(f"\n=== [{slot.slot}] {slot.arm} {slot.scenario}  {shown} $ {' '.join(argv)}")
            if slot.arm != "B0":
                probes += 1
            code = int(launch(argv, env))
            if code not in CLEARABLE or attempt == retries:
                break
            wait(RETRY_WAIT_SECONDS)
        if code not in CLEARABLE:
            injected = True
        if code == 0 and judged(queue.kind, slot.arm):
            run_id = find_run(label, slot.slot)
            if run_id:
                judge(run_id)
        result.tally = read_tally(labels, probes)
        row = Row(
            slot.slot,
            slot.pass_name,
            slot.scenario,
            slot.arm,
            code,
            attempt,
            result.tally.usd,
            rerun,
        )
        result.rows.append(row)
        log(row)
        print(f"=== [{slot.slot}] {row.outcome}; tally {result.tally.render()}", flush=True)
        if code in DISCARDS or code in CLEARABLE:
            if rerun:
                second.add((slot.scenario, slot.arm))
                if slot.scenario not in result.removed:
                    result.removed.append(slot.scenario)
            else:
                discarded.setdefault(slot.pass_name, []).append(slot)
        return None

    for index, slot in enumerate(block):
        reason = run_one(slot, len(block) - index, rerun=False)
        if reason:
            return stop(reason, block[index:])
        ends_pass = index + 1 == len(block) or block[index + 1].pass_name != slot.pass_name
        if ends_pass:
            again = discarded.pop(slot.pass_name, [])
            for j, retry in enumerate(again):
                print(f"--- re-running discarded slot {retry.slot} once (end of pass)")
                reason = run_one(retry, len(again) - j, rerun=True)
                if reason:
                    return stop(reason, again[j:] + block[index + 1 :])
    result.tally = read_tally(labels, probes)
    return result


def logged_probes(path: Path) -> int:
    """Probes an earlier invocation made: one per launch attempt of every arm but B0, read off
    its batch log, so a batch resumed over several nights tallies all of them."""
    if not path.is_file():
        return 0
    total = 0
    for line in path.read_text().splitlines()[1:]:
        cells = line.split("\t")
        if len(cells) >= 6 and cells[3] != "B0":
            total += int(cells[5])
    return total


def find_run(label: str, slot: int, root: Path = RUN_ROOT) -> str | None:
    """The newest run directory this batch launched for `slot`."""
    from evalharness.spend import manifests_of

    found = [
        m.get("run_id")
        for m in manifests_of(label, root)
        if (m.get("sweep") or {}).get("slot") == slot
    ]
    return str(found[-1]) if found and found[-1] else None


# --- the corpus of record (item 8) ----------------------------------------------------------


def corpus_record(state: Mapping[str, Any], agrees: bool, drift: str) -> dict[str, Any]:
    return {
        "rows": state.get("rows"),
        "documents": state.get("documents"),
        "sha256": state.get("sha256"),
        "body_sha256": state.get("body_sha256"),
        "holdout_chunks": state.get("holdout_chunks"),
        "agrees_with_the_tree": agrees,
        "drift": drift,
    }


# --- the CLI --------------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="faultline-batch",
        description="The headline run's and T7.3's batch runner (headline Addendum 1, items 8-9).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    q = sub.add_parser("queue", help="print a queue from its seed; commit it before the batch")
    q.add_argument("kind", choices=("headline", "t73"))
    q.add_argument("--seed", type=int, required=True)
    q.add_argument("--rerank-revision", default=None, help="E7's pinned cross-encoder commit")
    q.add_argument("--out", type=Path, required=True)

    r = sub.add_parser("run", help="run a committed queue, one slot at a time")
    r.add_argument("queue", type=Path)
    r.add_argument("--label", required=True, help="the batch id every manifest carries")
    r.add_argument("--stop-usd", type=float, required=True, help="57 for the headline, 114 T7.3")
    r.add_argument(
        "--also-count",
        action="append",
        default=[],
        metavar="LABEL",
        help="another batch id inside the same cap (the trial's), tallied with this one",
    )
    r.add_argument("--from-slot", type=int, default=1)
    r.add_argument("--to-slot", type=int, default=None)
    r.add_argument("--settle", type=int, default=SETTLE_SECONDS)
    r.add_argument("--postgres-dsn", default=None)
    r.add_argument(
        "--dry-run",
        action="store_true",
        help="no injection: the stamps, one world check, one corpus check, then every slot's "
        "command and switches printed (the build's dry run)",
    )

    c = sub.add_parser("corpus", help="read the ingested corpus and write its record (item 8)")
    c.add_argument("--postgres-dsn", default=None)
    c.add_argument("--out", type=Path, required=True)
    return p


def _dsn(value: str | None) -> str:
    from faultline.context.settings import ContextSettings

    return value or ContextSettings().postgres_dsn


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - the live path
    args = parser().parse_args(argv)
    if args.command == "queue":
        from evalharness import sweep

        if args.kind == "headline":
            dev = sweep.runnable(world="v2")
            both = sweep.runnable(world="v2", holdout=True)
            slots = headline_queue(dev, sorted(set(both) - set(dev)), args.seed)
        else:
            slots = t73_queue(t73_scenarios(), args.seed)
        queue = Queue(args.kind, args.seed, slots, args.rerank_revision)
        read_queue(render_queue(queue))
        args.out.write_text(render_queue(queue))
        print(f"{len(slots)} slot(s) -> {args.out}")
        return 0

    dsn = _dsn(args.postgres_dsn)
    if args.command == "corpus":
        from evalharness.corpusdrift import compare, seeded_rows, working_tree_rows
        from evalharness.freeze import corpus_state

        state = corpus_state(dsn)
        drift = compare(seeded_rows(dsn), working_tree_rows(None))
        record = corpus_record(state, drift.agrees, drift.render())
        args.out.write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps({k: v for k, v in record.items() if k != "drift"}, indent=2))
        ok = drift.agrees and not state.get("holdout_chunks")
        print("CORPUS OF RECORD READY" if ok else "NOT READY - see the record")
        return 0 if ok else 1

    from evalharness.freeze import corpus_state
    from faultline.agents.settings import AgentSettings

    if os.environ.get("FAULTLINE_TOOLS_WORLD") != "v2":
        print("REFUSED: FAULTLINE_TOOLS_WORLD must be v2 for this batch")
        return 3
    queue = read_queue(args.queue.read_text())
    default_model = AgentSettings().model

    def corpus() -> tuple[bool, str]:
        return corpus_frozen(corpus_state(dsn))

    def world() -> tuple[bool, str]:
        return world_ready(run_world_check, restart_quote, time.sleep)

    if args.dry_run:
        for name, check in (("stamps", stamps), ("corpus", corpus), ("world", world)):
            print(f"{name}: {check()}")
        known = arms(queue.rerank_revision)
        for s in queue.slots:
            arm = known[s.arm]
            shown = " ".join(f"{k}={v}" for k, v in sorted(arm.env.items()))
            remaining = len(queue.slots) - s.slot + 1
            print(f"{shown} {' '.join(slot_argv(s, arm, args.label, remaining, len(queue.slots)))}")
        return 0

    log_path = RUN_ROOT / f"BATCH-{args.label}.tsv"
    probes_before = sum(
        logged_probes(RUN_ROOT / f"BATCH-{name}.tsv") for name in [args.label, *args.also_count]
    )
    if not log_path.exists():
        log_path.write_text("slot\tpass\tscenario\tarm\toutcome\tattempts\trerun\ttally_usd\n")

    def log(row: Row) -> None:
        with log_path.open("a") as out:
            out.write(
                f"{row.slot}\t{row.pass_name}\t{row.scenario}\t{row.arm}\t{row.outcome}\t"
                f"{row.attempts}\t{int(row.rerun)}\t{row.tally_usd:.2f}\n"
            )

    def launch(cmd: list[str], env: dict[str, str]) -> int:
        return subprocess.run(cmd, env=env, check=False).returncode

    def judge(run_id: str) -> None:
        env = {**os.environ, **JUDGE_ENV}
        try:
            subprocess.run(["faultline-judge", run_id], env=env, check=False, timeout=600)
        except subprocess.TimeoutExpired:
            print(f"--- the judge did not finish on {run_id} in 600 s; not a headline axis")

    def read_tally(labels: list[str], probes: int) -> Tally:
        return tally(labels, probes, default_model, lambda i: steps_by_role(dsn, i))

    result = run_batch(
        queue,
        label=args.label,
        stop_usd=args.stop_usd,
        also_count=args.also_count,
        from_slot=args.from_slot,
        to_slot=args.to_slot,
        settle=args.settle,
        launch=launch,
        judge=judge,
        find_run=find_run,
        read_tally=read_tally,
        world=world,
        corpus=corpus,
        log=log,
        probes_before=probes_before,
    )
    print("\n".join(result.render()))
    return 1 if result.stopped else 0


def run_cli() -> None:  # pragma: no cover - console entry point
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover
    run_cli()
