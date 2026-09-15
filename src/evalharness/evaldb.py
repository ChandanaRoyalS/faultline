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
    "ablation",
    "observability_digest",
    "corpus_sha256",
    "corpus_body_sha256",
)
"""The behaviour-relevant settings, in the order T4.4 and T4.6 name them.

`runtime_version` covers *prompt versions* - it is a digest over every role system prompt and
every contract schema. `models` and `efforts` are the model map. `budget` is the context and cost
settings. `repeat_count` and `seed_policy` are T4.6's, and are absent from every run recorded
before it. `ablation` is T6.1's - the specialists withheld from the agent, `[]` for a full run -
and is absent from every run recorded before it, which `missing` records; an ablation run and a
full run therefore never share a fingerprint, and neither pools with a run made before the switch
existed without the difference being visible.

**`observability_digest` is T6.1's too, and closes a hole this table had from the start.**
A run's generation is named by `compose_digest` alone (`generations.world_key`), so **two
worlds differing only in what the agent can observe were one configuration here.** Harmless
until it was not: on 2026-09-08 fifteen runs were scored against a Tempo whose
`max_block_duration` made its search blind to the last five minutes - the window an investigation
asks about - and the fix moved
`observability_digest` and left `compose_digest` untouched. Without this input those fifteen runs
would share a fingerprint with every run made after the fix, which is the silent pooling the whole
table exists to prevent.

**Read off the freeze, which has recorded it since T7.15** - not a new measurement, a recorded
one that nothing was reading. `None` for the runs whose freeze predates the field, which
`missing` reports rather than defaulting. **The generation *name* still under-specifies the world**;
naming it properly would rename every generation in README, RESULTS and PLAN, and belongs in a
change of its own rather than in this docstring - `docs/QUEUE.md` Q31.

**`corpus_sha256` and `corpus_body_sha256` are Q61's, and close the same hole one layer over.**
Everything the paragraph above says about observability is true of the corpus, word for word: a
generation is named by `compose_digest` alone, so **two corpora were one configuration here**, and
a re-seed moves what every run afterwards can retrieve while moving no generation. Measured before
this input was added: the archive's 183 corpus-carrying runs are **six at 35 chunks over 7
documents** and **177 at 103 chunks over 25**, and they shared a configuration.

**Two inputs rather than one, because the two digests see different changes.** `sha256` hashes
`document_id|section` and sees a document added or removed; `body_sha256` hashes the text and sees
a rewrite under an unchanged heading, which `sha256` cannot see at all (Q36, Q45). The seed T6.5
needs carries both at once - postmortems are new documents, and nine drifted runbooks are
rewrites with identical shape - so one input would catch one of them.

**What this costs, measured rather than feared.** `eval_configs.fingerprint` is a stored primary
key, so every corpus-carrying manifest hashes to a **different value** after this change and a
re-ingest lands it under a new row. The worry that follows is that the archive gets re-partitioned
- and it does not: over all 548 manifests on disk the grouping is **byte-for-byte the same 38
groups with the same members**, only renamed. Every configuration in this archive was already
corpus-homogeneous, which is the same fact the scenario table's tripwire records from the other
side.

So the cost is names, not membership. `load` upserts on `run_id`, so a re-backfill repoints each
run and leaves the superseded config rows orphaned and harmless, and a database left half-loaded
holds **the same groups under two names** rather than genuinely mixed ones. Re-backfill anyway,
because two names for one configuration is a report that counts it twice.

**Adding the input is right even though it currently separates nothing.** It is a mechanism for
the next seed - the one T6.5 needs - not a repair of the last one, and a guard that has never had
to fire is the only kind worth having in place beforehand.
"""


class ConflictingOutcomeError(RuntimeError):
    """A manifest's outcome disagrees with the row already stored for that run."""


def outcome_reread(stored: str, manifest: dict[str, Any]) -> str | None:
    """Whether a stored outcome may be replaced by the manifest's current reading, and why.

    Returns the name of the correction that explains the disagreement, or `None` when nothing
    does - in which case the loader stops, because the realistic cause is a directory edited by
    hand and a benchmark's record must not absorb that quietly.

    **Two corrections are recognised, and both are `outcome_of`'s own.** Each is a *reading* of
    the record rather than an edit to it, each landed after rows had already been stored under the
    older reading, and each has an exact signature. Anything else that disagrees is still a
    conflict.

    **1. A discard that never injected reads as a refusal (2026-09-04).** Gate refusals were
    written as discards until that day. Rows loaded before the reading existed say `discarded`;
    the loader met one on 2026-09-11 at the end of dev sweep 12 and refused to load anything -
    correctly, given what it knew, and wrongly, given what the repository knew. The signature: the
    manifest still carries the `discarded` block it was written with, and has no `injected_at`.

    **2. A scored run whose budget did not bind reads as invalid (Q33, 2026-09-14).**
    `outlived_its_budget` compares the run's own recorded latency against its own recorded
    budget, and `outcome_of` answers `invalid` when it overran - because the question that column
    answers is *may these numbers be used*. One run in the archive meets it:
    `20260910T002657Z-ad-memory-squeeze`, **6596 s against a 600 s budget**, stored as `scored`
    before the rule existed. The loader refused the whole backfill on it 2026-09-15, which is the
    same shape as the first case a year's worth of commits later.

    **The signature here is exact for the same reason.** It applies only when the manifest carries
    a `score` block, carries **no** `invalid` block of its own, and `outlived_its_budget` says so.
    A hand-written `invalid` block returns at `outcome_of`'s first line and never reaches this
    branch, so a directory edited by hand still stops the loader - which is the property this
    function exists to keep.
    """
    if (
        stored == "discarded"
        and outcome_of(manifest) == "refused"
        and manifest.get("discarded")
        and not manifest.get("injected_at")
    ):
        return "a discard that never injected reads as a refusal (2026-09-04 correction)"
    if (
        stored == "scored"
        and outcome_of(manifest) == "invalid"
        and manifest.get("score")
        and not manifest.get("invalid")
        and outlived_its_budget(manifest)
    ):
        return "a run whose budget did not bind reads as invalid (Q33, 2026-09-14 correction)"
    return None


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
    if key == "observability_digest":
        # The freeze's, not the repository's: the question is what this run executed against.
        return ((manifest.get("freeze") or {}).get("world") or {}).get("observability_digest")
    if key in {"corpus_sha256", "corpus_body_sha256"}:
        # The freeze's corpus block, which is what this run retrieved from (Q61). Absent for the
        # 289 run directories with no freeze corpus block, and `body_sha256` is absent for every
        # run recorded so far - it landed 2026-09-14, after the newest scored run. `missing`
        # reports both rather than defaulting, which is this module's whole rule.
        corpus = (manifest.get("freeze") or {}).get("corpus") or {}
        return corpus.get(key.removeprefix("corpus_"))
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


def outlived_its_budget(manifest: dict[str, Any]) -> bool:
    """Did the investigation run longer than the budget the run itself declares? (Q33)

    **A reading of the record, not an edit to it** - the same standing as the `refused` recovery
    below, and for the same reason: `metrics.latency.investigation_seconds` and
    `budget.wall_clock_seconds` are both on every manifest that has them, so the comparison was
    always available and nobody had made it.

    `20260910T002657Z-ad-memory-squeeze` recorded **6596 s against a 600 s budget** and a 1800 s
    harness kill, and neither fired: the machine slept, and macOS's monotonic clock stops with it.
    The run is `scored`, it is in arm B's fingerprint, and `faultline-compare`'s latency figure for
    that arm is distorted by it. A budget that did not bind is the same kind of fact as T4.1b's
    silent filter, which already reads `invalid`.

    **Measured across every manifest on disk before this rule was written: 1 of 245 scored runs.**
    That one is the run that motivated the rule, at 11x its budget. This is not a rule that
    reclassifies a population - it is a rule that catches an outlier nobody had a name for, and
    knowing the count before writing it is what makes that claim checkable.

    Absent fields mean **no**. A manifest without the latency block or without a budget is not
    asserted to have overrun; it is a manifest that cannot answer, and defaulting to `invalid`
    would reclassify the archive on a technicality.
    """
    latency = ((manifest.get("metrics") or {}).get("latency") or {}).get("investigation_seconds")
    declared = (manifest.get("budget") or {}).get("wall_clock_seconds")
    if latency is None or not declared:
        return False
    return float(latency) > float(declared)


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
    if manifest.get("score"):
        return "invalid" if outlived_its_budget(manifest) else "scored"

    # **The fallthrough asks the same question, and it did not.** It read
    # `else "discarded"`, so a manifest carrying no outcome label at all became a discard by
    # default - and the pre-flight refusal path wrote exactly that shape, a manifest with a
    # `preflight` block and nothing else. Thirty of them landed on 2026-09-04 and the recorded
    # discard rate went from 16.7% to 28.6% overnight, which is the inflation this function was
    # written to stop, arriving through its own default two days later.
    #
    # The claim that this function protected the figure was made in dev sweep 9's document and in
    # `run.py`'s comment, from reading the branch above and not the line below it. Both are
    # corrected in this change. **A recovery that covers the labelled case and defaults the
    # unlabelled one to the very label it exists to correct is not a recovery.**
    return "discarded" if manifest.get("injected_at") else "refused"


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

    written = {"configs": 0, "runs": 0, "reread": 0}
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for row in rows:
            cur.execute("SELECT outcome FROM eval_runs WHERE run_id = %s", (row.run_id,))
            found = cur.fetchone()
            if found and found[0] != row.outcome:
                why = outcome_reread(found[0], row.manifest)
                if why is None:
                    raise ConflictingOutcomeError(
                        f"{row.run_id} is stored as {found[0]} and its manifest now reads "
                        f"{row.outcome}. One of the two is wrong and this loader will not choose."
                    )
                print(f"  reread {row.run_id}: {found[0]} -> {row.outcome} - {why}")
                written["reread"] += 1

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
    reread = f", {written['reread']} outcome(s) reread" if written.get("reread") else ""
    print(f"\nloaded {written['runs']} run(s), {written['configs']} new configuration(s){reread}")
    return 0


def run_cli() -> None:  # pragma: no cover - console entry point
    import sys

    sys.exit(main())
