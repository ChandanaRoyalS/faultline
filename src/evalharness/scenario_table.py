"""The per-scenario table README carries up top (T5.3, audited under T5.6).

The execution plan's T5.3 names *"a README with the 10-scenario eval table up top"*. README had a
Results section - a long one, correct, and two hundred lines down - whose tables were **per fault
class**, and no table anywhere listed the scenarios one per row. A reader who wanted to know how
often `cart-bad-image-tag` was named correctly had to open `evals/runs/` and count.

This module counts, and README embeds what it prints between two markers.
`tests/test_scenario_table.py` regenerates the table from the tree and fails when the embedded copy
differs - the same shape as `test_results_staleness`, for the same reason: **a snapshot goes stale,
and the fix for a snapshot is a check that fails when it does**, not a better snapshot.

## What is counted, and what is not

- **Only scored runs** (`evaldb.outcome_of == "scored"`): a discarded, refused, paused or invalid
  run produced no result and is not a sample. Discards stay on disk and are counted in RESULTS.md.
- **Never a demo run** (`run.counts_toward_aggregates`): a run made to be watched is not a sample.
- **Never a baseline run.** B0's control arm is scored on the same axes; it has its own column
  in RESULTS.md and no place in a table about the pipeline.
- **Only the current world.** Runs on `4a7690c6fdda` and `299d791c5e0d` were against a world that
  no longer exists, and a table that summed them with today's would print two worlds as one -
  the misreading `generations.group_by_generation` exists to prevent. The holdout scenarios have
  **no** run on the current world and cannot get one - entry 4 is blocked by ADR-0029 - and the
  table says so with a zero rather than by borrowing.
- **The figures are at one stamp.** A prompt change is a different pipeline (ADR-0022), so the
  correctness columns are over runs at the stamp the repository ships. Two trailing columns pool
  every stamp on this world, labelled *context, not a figure*: they exist so a reader can see how
  thin `n` is at any one stamp - RESULTS.md's variance finding is that a single run is not
  reproducible to ±1 scenario, and the pooled count is the size of that problem, not a cure for it.
- **Abstentions are not errors and not successes.** `class` is correct / answered, where answered
  excludes abstentions; `abst` counts them. Coverage and accuracy stay separate (ADR-0022 §1.2).
- **`service`** is scored since T4.2 only; runs from before it carry no service block and are
  absent from that column's denominator, which is why it can be smaller than `n`.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evalharness.evaldb import outcome_of
from evalharness.generations import CURRENT_OBSERVABILITY, WORLD_90E, generation_of
from evalharness.run import counts_toward_aggregates
from evalharness.scenario import Scenario

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS = REPO_ROOT / "evals" / "runs"
SCENARIOS = REPO_ROOT / "evals" / "scenarios"

BEGIN = "<!-- scenario-table:begin -->"
END = "<!-- scenario-table:end -->"
"""README's markers. Everything between them is this module's output and nobody else's."""

CURRENT_WORLD = WORLD_90E
"""The reference-platform generation every published figure carries. A run on another platform
has a different key (`generations.world_key`) and is not in this table."""


@dataclass(frozen=True, slots=True)
class Tally:
    """Counts over one set of runs."""

    n: int = 0
    class_answered: int = 0
    class_correct: int = 0
    abstained: int = 0
    service_answered: int = 0
    service_correct: int = 0

    @staticmethod
    def over(manifests: list[dict[str, Any]]) -> Tally:
        answered = correct = abstained = svc_answered = svc_correct = 0
        for m in manifests:
            score = m.get("score") or {}
            fault = score.get("fault_class") or {}
            if fault.get("abstained"):
                abstained += 1
            else:
                answered += 1
                correct += 1 if fault.get("correct") else 0
            service = score.get("service")
            if service and not service.get("abstained"):
                svc_answered += 1
                svc_correct += 1 if service.get("correct") else 0
        return Tally(len(manifests), answered, correct, abstained, svc_answered, svc_correct)

    def __add__(self, other: Tally) -> Tally:
        return Tally(
            self.n + other.n,
            self.class_answered + other.class_answered,
            self.class_correct + other.class_correct,
            self.abstained + other.abstained,
            self.service_answered + other.service_answered,
            self.service_correct + other.service_correct,
        )


@dataclass(frozen=True, slots=True)
class ScenarioRow:
    scenario_id: str
    split: str
    at_stamp: Tally
    """Runs at the prompt stamp the repository ships - the figures that describe *this* pipeline."""
    on_world: Tally
    """Every qualifying run on the current world at any stamp - context, not a figure."""


def _manifests(runs: Path) -> list[dict[str, Any]]:
    return [
        json.loads(p.read_text())
        for p in sorted(runs.glob("*/manifest.json"))
        if not p.parent.name.startswith(".")
    ]


def _qualifies(manifest: dict[str, Any], world: str, observability: str | None = None) -> bool:
    return (
        counts_toward_aggregates(manifest)
        # The pipeline arm only. A B0 baseline run (`manifest["baseline"]`, stamp
        # `+baseline:B0`) is scored on the same axes and would otherwise be summed in as if
        # the control were the system - RESULTS.md gives the baselines their own column.
        and not manifest.get("baseline")
        # **And the full arm only.** A `--without traces` run is a different pipeline in exactly
        # the sense the line above means it: T6.1 put `ablation` in `evaldb.FINGERPRINT_INPUTS`
        # *"so an ablation run can never pool with a full run"*, and this table has its own filter
        # that did not know about it. Arm B's first six runs landed straight into arm A's column
        # on 2026-09-10 - `ad-memory-squeeze` read `n = 5` and `3 / 5` on the service axis, four
        # of those runs being an arm measuring the opposite thing. **Third time**: the same hole
        # took `observability_digest` two days earlier and the B0 arm before that. A key joining
        # the fingerprint is not the same as a key joining this filter, and the fingerprint is not
        # what a reader of README sees.
        and not (manifest.get("ablation") or [])
        and outcome_of(manifest) == "scored"
        and generation_of(manifest).world == world
        and _observability_agrees(manifest, observability)
    )


def _observability(manifest: dict[str, Any]) -> str | None:
    return ((manifest.get("freeze") or {}).get("world") or {}).get("observability_digest")


def _observability_agrees(manifest: dict[str, Any], expected: str | None) -> bool:
    """Whether this run's observability config is the one the current figures describe.

    **A generation is named by `compose_digest` alone, and that is not the whole world (T6.1).** On
    2026-09-08 fifteen runs were scored against a Tempo whose search was blind to the last five
    minutes; the fix moved `observability_digest` and left `compose_digest` where it was, so those
    runs and every run made after carry the same generation name. They are not the same world to an
    agent, and this table's headline figures are about what an agent got right.

    **A manifest that never recorded the digest is not excluded.** Absent means unknown, not
    different - the same rule `evaldb.fingerprint` applies through `missing`, and the reason the
    first version of this function was wrong: it dropped every run whose freeze predates T7.15,
    which is most of the record. Only a *recorded and differing* digest excludes a run, and it
    excludes it from the at-stamp figures alone; `evals/runs/` and the pooled column keep it.

    Naming the generation properly is `docs/QUEUE.md` Q31.
    """
    recorded = _observability(manifest)
    return expected is None or recorded is None or recorded == expected


def rows(
    stamp: str,
    runs: Path = RUNS,
    scenarios: Path = SCENARIOS,
    world: str = CURRENT_WORLD,
    observability: str | None = CURRENT_OBSERVABILITY,
) -> list[ScenarioRow]:
    """One row per unblocked scenario, dev first, then holdout, alphabetical within each."""
    # The top-level files only: `evals/scenarios/examples/` is the schema's worked example and
    # `load_catalog` recurses. A blocked scenario releases its slot and is not a row.
    loaded = (Scenario.from_yaml(p) for p in sorted(scenarios.glob("*.yaml")))
    catalog = [s for s in loaded if not s.blocked]
    catalog.sort(key=lambda s: (s.split != "dev", s.id))
    on_world = [m for m in _manifests(runs) if _qualifies(m, world)]
    qualifying = [m for m in on_world if _qualifies(m, world, observability)]

    out: list[ScenarioRow] = []
    for scenario in catalog:
        # **The two columns ask different questions, so they filter differently.** The pooled
        # column is context - every stamp on this compose world - and keeps runs whose
        # observability differs, because dropping them would hide runs that happened.
        # The at-stamp columns are the figures, and ask for both digests.
        mine = [m for m in on_world if m.get("scenario_id") == scenario.id]
        at_stamp = [
            m
            for m in qualifying
            if m.get("scenario_id") == scenario.id
            and str((m.get("score") or {}).get("runtime_version", "")).endswith(f"prompts:{stamp}")
        ]
        out.append(ScenarioRow(scenario.id, scenario.split, Tally.over(at_stamp), Tally.over(mine)))
    return out


def _cell(correct: int, answered: int) -> str:
    return "—" if answered == 0 else f"{correct} / {answered}"


def _repeats_sentence(table: list[ScenarioRow]) -> str:
    """How many runs each dev scenario got at this stamp, read off the rows rather than asserted.

    **Because the hand-written version went stale the moment it mattered.** The preamble said
    *"R=1 everywhere, so no row is reproducible to ±1"* through every sweep in this repository, and
    then arm A of dev sweep 12 landed thirty runs at R = 3 beside a sentence still saying R = 1.
    A generated block that carries a hand-maintained claim about its own contents has one claim
    nobody regenerates.
    """
    counts = sorted({r.at_stamp.n for r in table if r.split == "dev" and r.at_stamp.n})
    if not counts:
        return "No dev scenario has a run at this stamp."
    if len(counts) == 1:
        n = counts[0]
        if n == 1:
            return "R = 1 on every dev scenario with a run, so no row is reproducible to +/-1."
        return (
            f"R = {n} on every dev scenario with a run, which is what makes a row a small\n"
            "sample rather than a single observation (RESULTS.md)."
        )
    return (
        f"**Dev scenarios got different numbers of runs at this stamp ({counts}).** That is a "
        "sweep the world did not complete, not a design - see the sweep's own divergence report."
    )


def render(stamp: str, table: list[ScenarioRow], world: str = CURRENT_WORLD) -> str:
    """The Markdown README embeds, markers included. Deterministic for a given tree."""
    lines = [
        BEGIN,
        f"Per scenario. The first four columns are at `prompts:{stamp}`, the stamp this",
        f"repository ships, on the current world (`{world}`): scored runs only, demos, the B0",
        "arm and ablation arms excluded. `class` and `service` are correct / answered;",
        "abstentions are counted in `abst`, not as wrong. The last two columns pool every stamp",
        "on this world - **context, not a figure**: a prompt change is a different pipeline, and",
        "the pooled column is here so a reader can see how thin `n` is at any one stamp. Holdout",
        "scenarios have no run on this world at all; the zeros are the record.",
        _repeats_sentence(table),
        "",
        "| scenario | split | n | class | abst | service | n, all stamps | class, all stamps |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    total_stamp = Tally()
    total_world = Tally()
    for r in table:
        a, w = r.at_stamp, r.on_world
        total_stamp, total_world = total_stamp + a, total_world + w
        lines.append(
            f"| `{r.scenario_id}` | {r.split} | {a.n} | "
            f"{_cell(a.class_correct, a.class_answered)} | {a.abstained} | "
            f"{_cell(a.service_correct, a.service_answered)} | "
            f"{w.n} | {_cell(w.class_correct, w.class_answered)} |"
        )
    a, w = total_stamp, total_world
    lines.append(
        f"| **all** | | **{a.n}** | **{_cell(a.class_correct, a.class_answered)}** | "
        f"**{a.abstained}** | **{_cell(a.service_correct, a.service_answered)}** | "
        f"**{w.n}** | **{_cell(w.class_correct, w.class_answered)}** |"
    )
    lines.append("")
    lines.append(
        "Regenerate with `uv run python -m evalharness.scenario_table --write`; "
        "`tests/test_scenario_table.py` fails when this block and the tree disagree."
    )
    lines.append(END)
    return "\n".join(lines)


def current_stamp() -> str:
    from faultline.agents.stamp import prompt_digest

    return prompt_digest()


def embedded(readme: Path = REPO_ROOT / "README.md") -> str | None:
    """The block README carries now, markers included, or `None` if there is none."""
    text = readme.read_text()
    if BEGIN not in text or END not in text:
        return None
    start = text.index(BEGIN)
    return text[start : text.index(END, start) + len(END)]


def main(argv: list[str] | None = None) -> int:
    """Print the block. With `--write`, replace README's block in place."""
    args = list(sys.argv[1:] if argv is None else argv)
    stamp = current_stamp()
    block = render(stamp, rows(stamp))
    if "--write" in args:
        readme = REPO_ROOT / "README.md"
        have = embedded(readme)
        if have is None:
            print("README.md has no scenario-table markers; nothing written", file=sys.stderr)
            return 2
        readme.write_text(readme.read_text().replace(have, block))
        print(f"README.md: scenario table rewritten at prompts:{stamp}")
        return 0
    print(block)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
