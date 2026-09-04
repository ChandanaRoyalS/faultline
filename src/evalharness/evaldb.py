"""The eval database: config fingerprints, and every run that ran under one (T4.4).

T4.4 asks for *"every eval run [persisted] with config fingerprint (prompt versions, model,
context settings)"* and for the fingerprint to be *"a hash of all behavior-relevant settings -
including repeat count R, judge version, and seed policy"*.

## The fingerprint is over what was present, and says what was not

The obvious implementation hashes a fixed list of settings. It is wrong here, and the reason is
the history: these manifests span six generations of the harness, and the earlier ones do not
carry a freeze block, a budget block, or any of T4.6's three fields - because those did not exist
when the runs happened. Hashing a fixed list would mean substituting a default for an absent
input, and **a default is a claim about a run that nobody made**.

So `fingerprint` hashes the inputs that are *present*, and `missing` records the rest. The
property this buys is the one a comparison needs:

> **Two runs share a fingerprint only when the same inputs were present and equal.**

A run recorded before an input existed therefore cannot collide with one recorded after it, and a
comparison across that boundary is visibly a comparison of two different configurations rather
than an accidental average. The alternative - filling in defaults - produces one fingerprint
spanning both eras and a report that silently compares them.

## Every outcome is a row

`scored`, `discarded`, `paused`, `invalid`. ADR-0022 §3.3 keeps discard directories so that *the
number of runs is a fact nobody can hide by tidying*, and a table holding only successes would
answer "how often does the harness work" with "always". The discard rate is a headline property
of a benchmark, not an operational detail.

## Loading is idempotent, and never overwrites a scored row with less

`load` upserts on `run_id`. Re-running the backfill is safe, and re-loading a manifest that has
since gained a judge block or a metrics block updates the row. What it will not do is silently
replace a row's outcome: a run recorded as `scored` whose manifest later reads `discarded` is a
contradiction in the record and is raised rather than resolved, because whichever one is wrong,
guessing is worse than stopping.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

FINGERPRINT_INPUTS = (
    "baseline",
    "runtime_version",
    "models",
    "efforts",
    "budget",
    "world_generation",
    "judge_version",
    "repeat_count",
    "seed_policy",
)
"""The behaviour-relevant settings, in the order T4.4 and T4.6 name them.

`runtime_version` covers *prompt versions* - it is a digest over every role system prompt and
every contract schema. `models` and `efforts` are the model map. `budget` is the context and cost
settings. The last three are T4.6's, and are absent from every run recorded before it.
"""


class ConflictingOutcomeError(RuntimeError):
    """A manifest's outcome disagrees with the row already stored for that run."""


@dataclass(frozen=True, slots=True)
class Config:
    """One distinct behaviour-relevant configuration."""

    fingerprint: str
    settings: dict[str, Any]
    missing: list[str]
    runtime_version: str | None

    @property
    def complete(self) -> bool:
        """Every input the fingerprint knows about was present. **Not a quality judgement** - an
        incomplete fingerprint is honest about a run from before those inputs existed."""
        return not self.missing


def fingerprint(manifest: dict[str, Any]) -> Config:
    """The config fingerprint for one run manifest.

    Canonical JSON with sorted keys, so two equal settings objects hash equal whatever order the
    manifest wrote them in. Twelve hex characters, matching the stamp's own `DIGEST_CHARS` - long
    enough to be unambiguous in a table and not a security boundary.
    """
    present: dict[str, Any] = {}
    missing: list[str] = []
    for key in FINGERPRINT_INPUTS:
        value = _setting(manifest, key)
        if value is None:
            missing.append(key)
        else:
            present[key] = value
    canonical = json.dumps(present, sort_keys=True, separators=(",", ":"), default=str)
    return Config(
        fingerprint=hashlib.sha256(canonical.encode()).hexdigest()[:12],
        settings=present,
        missing=missing,
        runtime_version=present.get("runtime_version"),
    )


def _setting(manifest: dict[str, Any], key: str) -> Any:
    """One fingerprint input, or `None` when the manifest does not carry it.

    The lookups differ because the manifest grew in layers: `models` and `budget` are top level,
    `runtime_version` moved into the score block when scoring arrived, and `world_generation`
    lives under `comparability` since the freeze path was wired in at T7.55.
    """
    score = manifest.get("score") or {}
    if key == "runtime_version":
        recorded = score.get("runtime_version")
        if recorded:
            return recorded
        # **The freeze's stamp is not a fallback for a baseline run.** `freeze.runtime_version` is
        # the *agent's* digest over role prompts and contract schemas, taken before injection as
        # provenance of the harness code. A scored run overwrites it from the trajectory, so the
        # distinction is invisible - until a run is **discarded**, which has no score block and on
        # this catalog happens about a third of the time. A discarded B0 run would then be
        # recorded, and its `eval_configs` row permanently labelled, under the runtime of the
        # pipeline it is a control for: the one confusion this table exists to prevent, and worse
        # than a NULL because it reads as authoritative (cf. the `compare.arm()` fix, #165).
        #
        # `None` rather than `baselines.BASELINE_RUNTIME`: that constant is the *current* version,
        # so a discarded B0 v1 run would be stamped `B0.2` and become poolable with v2 - exactly
        # the pooling the version marker exists to prevent. The run did not record what ran and
        # the manifest cannot reconstruct it, so "not recorded" is the true answer.
        #
        # Agent runs store `baseline: null`, which is falsy, so their fallback is unchanged.
        if manifest.get("baseline"):
            return None
        return (manifest.get("freeze") or {}).get("runtime_version")
    if key == "world_generation":
        return (manifest.get("comparability") or {}).get("generation")
    if key == "judge_version":
        return (manifest.get("judge") or {}).get("judge_model")
    if key == "baseline":
        # T4.7: a baseline is a different configuration from the agent by definition, and this
        # is what keeps them from sharing a fingerprint. `None` for an agent run, so agent runs
        # recorded before baselines existed are unaffected - the input is simply missing for
        # them, which `missing` records and the hash reflects.
        return manifest.get("baseline")
    if key in {"repeat_count", "seed_policy"}:
        # T4.6's, and deliberately not defaulted. A run that never stated its repeat count has
        # not claimed to be a single observation; it has claimed nothing, and `missing` says so.
        return manifest.get(key)
    return manifest.get(key)


def outcome_of(manifest: dict[str, Any]) -> str:
    """`scored`, `invalid`, `refused`, `discarded` or `paused`.

    Order matters: a run can be both scored and invalid - T4.1b's silent-filter case produces a
    score and then refuses it - and `invalid` is the answer, because the question this column
    answers is *may these numbers be used*.

    **`refused` is recovered from `injected_at`, not from the label on disk**, and that recovery
    is the point. Gate refusals were written as discards until 2026-09-04, and the correction is a
    *reading* of the record rather than an edit to it: a discard is a run that **happened** and
    produced no result, and a manifest with no `injected_at` never started.

    Measured over the 132 runs on disk when this was found: **44 discards, of which 22 had never
    injected anything** - 10 `baseline gate refused`, 10 `pipeline-down`, 2 others. So the
    discard rate this repository quoted, budgeted sweeps against, and recorded in `docs/PLAN.md`
    as *"a headline property of this harness"* - **33%** - was double the truth of **16.7%**.
    `HeadroomExhaustedError` had already made exactly this argument for itself and carried
    `is_pause`; nothing carried it for the other refusals.

    Nothing on disk is rewritten. Those 22 manifests keep the words they were written with.
    """
    if manifest.get("invalid"):
        return "invalid"
    if manifest.get("refused"):
        return "refused"
    if manifest.get("paused"):
        return "paused"
    if manifest.get("discarded"):
        # The retroactive half. `injected_at` is on every manifest ever written, so a refusal
        # mislabelled as a discard is distinguishable now without touching the file.
        return "discarded" if manifest.get("injected_at") else "refused"
    return "scored" if manifest.get("score") else "discarded"


@dataclass(frozen=True, slots=True)
class Row:
    """One `eval_runs` row, flattened from a manifest."""

    run_id: str
    scenario_id: str
    outcome: str
    config: Config
    values: dict[str, Any] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)


def row_of(manifest: dict[str, Any], run_id: str | None = None) -> Row:
    """Flatten one manifest into the columns a comparison groups and averages on."""
    score = manifest.get("score") or {}
    triage = score.get("triage") or {}
    fault = score.get("fault_class") or {}
    fix = score.get("fix_class") or {}
    latency = ((manifest.get("metrics") or {}).get("latency") or {}).get("investigation_ms")
    identifier = run_id or manifest.get("run_id") or ""
    return Row(
        run_id=str(identifier),
        scenario_id=str(manifest.get("scenario_id", "")),
        outcome=outcome_of(manifest),
        config=fingerprint(manifest),
        values={
            "split": manifest.get("split"),
            "scenario_fingerprint": manifest.get("scenario_fingerprint"),
            "started_at": manifest.get("started_at"),
            "finished_at": manifest.get("finished_at"),
            "discard_reason": (manifest.get("discarded") or {}).get("reason"),
            "invalid_reason": (manifest.get("invalid") or {}).get("reason"),
            "trajectory_id": score.get("trajectory_id"),
            "runtime_version": score.get("runtime_version"),
            "world_generation": (manifest.get("comparability") or {}).get("generation"),
            "repeat_count": manifest.get("repeat_count"),
            "judge_version": (manifest.get("judge") or {}).get("judge_model"),
            "seed_policy": manifest.get("seed_policy"),
            "cost_usd": score.get("cost_usd"),
            "tokens_in": score.get("tokens_in"),
            "tokens_out": score.get("tokens_out"),
            "latency_ms": latency,
            "reached_a_class": score.get("reached_a_class"),
            "fault_class_truth": fault.get("truth"),
            "fault_class_returned": fault.get("returned"),
            "fault_class_correct": fault.get("correct"),
            "fault_class_abstained": fault.get("abstained"),
            "fix_class_truth": fix.get("truth"),
            "fix_class_returned": fix.get("returned"),
            "fix_class_correct": fix.get("correct"),
            "fix_class_abstained": fix.get("abstained"),
            "triage_recall": triage.get("recall"),
            "triage_precision": triage.get("precision"),
        },
        manifest=manifest,
    )


def read_runs(root: Path) -> list[Row]:
    """Every manifest under `root`, flattened, in run order.

    A manifest with no `run_id` takes its directory name, which is what the run id is derived
    from anyway. Two of the 128 recorded manifests predate the field.
    """
    rows: list[Row] = []
    for path in sorted(root.glob("*/manifest.json")):
        manifest = json.loads(path.read_text())
        rows.append(row_of(manifest, run_id=manifest.get("run_id") or path.parent.name))
    return rows


COLUMNS = (
    "run_id",
    "scenario_id",
    "split",
    "scenario_fingerprint",
    "started_at",
    "finished_at",
    "outcome",
    "discard_reason",
    "invalid_reason",
    "trajectory_id",
    "runtime_version",
    "config_fingerprint",
    "world_generation",
    "repeat_count",
    "judge_version",
    "seed_policy",
    "cost_usd",
    "tokens_in",
    "tokens_out",
    "latency_ms",
    "reached_a_class",
    "fault_class_truth",
    "fault_class_returned",
    "fault_class_correct",
    "fault_class_abstained",
    "fix_class_truth",
    "fix_class_returned",
    "fix_class_correct",
    "fix_class_abstained",
    "triage_recall",
    "triage_precision",
    "manifest",
)


def load(dsn: str, rows: list[Row]) -> dict[str, int]:
    """Upsert configs and runs. Idempotent; returns what changed.

    Raises `ConflictingOutcomeError` when a stored run's outcome disagrees with the manifest
    being loaded. Whichever of the two is wrong, guessing is worse than stopping - and the
    realistic cause is a directory edited by hand, which is exactly the thing a benchmark's
    record must not absorb quietly.
    """
    import psycopg

    written = {"configs": 0, "runs": 0}
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for row in rows:
            cur.execute("SELECT outcome FROM eval_runs WHERE run_id = %s", (row.run_id,))
            found = cur.fetchone()
            if found and found[0] != row.outcome:
                raise ConflictingOutcomeError(
                    f"{row.run_id} is stored as {found[0]} and its manifest now reads "
                    f"{row.outcome}. One of the two is wrong and this loader will not choose."
                )

            cur.execute(
                "INSERT INTO eval_configs (fingerprint, first_seen, runtime_version, settings, "
                "missing) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (fingerprint) DO NOTHING",
                (
                    row.config.fingerprint,
                    row.values.get("started_at") or datetime.now().isoformat(),
                    row.config.runtime_version,
                    json.dumps(row.config.settings, default=str),
                    json.dumps(row.config.missing),
                ),
            )
            written["configs"] += cur.rowcount if cur.rowcount > 0 else 0

            # By name, never by slice. An index-sliced value list is one column insertion away
            # from writing a triage recall into a cost field, and it fails silently because both
            # are floats.
            named: dict[str, Any] = {
                **row.values,
                "run_id": row.run_id,
                "scenario_id": row.scenario_id,
                "outcome": row.outcome,
                "config_fingerprint": row.config.fingerprint,
                "manifest": json.dumps(row.manifest, default=str),
            }
            missing_columns = [name for name in COLUMNS if name not in named]
            if missing_columns:  # pragma: no cover - a schema/flattener drift guard
                raise RuntimeError(f"row_of produced no value for {missing_columns}")
            values = [named[name] for name in COLUMNS]
            updates = ", ".join(f"{name} = EXCLUDED.{name}" for name in COLUMNS[1:])
            cur.execute(
                f"INSERT INTO eval_runs ({', '.join(COLUMNS)}) "
                f"VALUES ({', '.join(['%s'] * len(COLUMNS))}) "
                f"ON CONFLICT (run_id) DO UPDATE SET {updates}",
                values,
            )
            written["runs"] += 1
        conn.commit()
    return written


def summarise(rows: list[Row]) -> list[str]:
    """What a backfill found, in the terms a reader needs to judge the history.

    Printed rather than asserted: this is a description of a record that already exists, and the
    counts it reports - how many configurations, how many runs carry an incomplete fingerprint -
    are findings about the past rather than conditions on the present.
    """
    configs: dict[str, Config] = {}
    outcomes: dict[str, int] = {}
    for row in rows:
        configs.setdefault(row.config.fingerprint, row.config)
        outcomes[row.outcome] = outcomes.get(row.outcome, 0) + 1
    incomplete = [c for c in configs.values() if not c.complete]
    lines = [
        f"{len(rows)} run(s) across {len(configs)} configuration(s)",
        "  outcomes: " + ", ".join(f"{n} {name}" for name, n in sorted(outcomes.items())),
        f"  {len(incomplete)} configuration(s) have an incomplete fingerprint - inputs that did "
        "not exist when they ran",
    ]
    for config in sorted(incomplete, key=lambda c: len(c.missing), reverse=True)[:5]:
        lines.append(f"    {config.fingerprint}  missing: {', '.join(config.missing)}")
    return lines


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - console entry point
    """`faultline-eval-db summary` and `faultline-eval-db load`.

    `summary` reads the run tree and prints what a backfill would find, touching no database.
    It exists so the answer to *"what is in this record"* does not require a running Postgres,
    and so a backfill can be inspected before it is performed.
    """
    import argparse

    from faultline.context.settings import ContextSettings

    parser = argparse.ArgumentParser(
        prog="faultline-eval-db",
        description="The eval database: load run manifests, and describe what they contain (T4.4).",
    )
    parser.add_argument("command", choices=("summary", "load"))
    parser.add_argument("--runs", default="evals/runs", type=Path)
    parser.add_argument("--postgres-dsn", default=None)
    args = parser.parse_args(argv)

    rows = read_runs(args.runs)
    for line in summarise(rows):
        print(line)
    if args.command == "summary":
        return 0

    # The same resolution every other harness command uses (`run.py`): the flag, then
    # pydantic-settings, which reads the environment and falls back to the local dev DSN. A
    # command that invented its own lookup would be one more thing to remember, and this one
    # invented an env var nothing else in the repo sets.
    dsn = args.postgres_dsn or ContextSettings().postgres_dsn
    import psycopg

    try:
        written = load(dsn, rows)
    except ConflictingOutcomeError as clash:
        print(f"\nREFUSED: {clash}")
        return 3
    except psycopg.OperationalError as unreachable:
        # A traceback here says "you typed something wrong"; the truth is almost always that
        # the world is not up. The summary above already printed, so the reader has the answer
        # to the question they were probably asking anyway.
        print(f"\nREFUSED: the database is not reachable - {unreachable}")
        print("The summary above needed no database. `docker compose up -d postgres` and retry.")
        return 2
    print(f"\nloaded {written['runs']} run(s), {written['configs']} new configuration(s)")
    return 0


def run_cli() -> None:  # pragma: no cover - console entry point
    import sys

    sys.exit(main())
