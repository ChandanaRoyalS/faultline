"""T7.3's ablation analysis, exactly as `PREREGISTRATION-T7.3.md` fixed it.

Standard library only, so anyone with Python 3.10+ and this repository's `evals/runs/` can
reproduce every figure in the nine `ABLATION-2026-10-15-E<n>-*.md` reports and in
`docs/ABLATIONS.md`:

    python3 evals/runs/analysis_t73_v2.py evals/runs              # every table
    python3 evals/runs/analysis_t73_v2.py evals/runs --block E3   # one report's generated block

What it reads: every `evals/runs/*/manifest.json` whose `sweep.id` is `t73-v2` (the batch), the
same for `headline-v2` (the A/A check's other half, F only), and
`docs/evidence/t7.3/trial/e2-radius-by-scenario.tsv` (E2, which was not run). Nothing else.

**One run's facts and the statistics are the headline script's**, imported from beside this file
(`analysis_headline_v2.py`): the same outcome reading (Q33 included), the same per-axis labels,
the same Wilson and bootstrap. Decisions the registration left open, made here once:

- **A configuration is read off the manifest**: `baseline: b1` is E1; otherwise the one key in
  `ablation_config` names the arm (Addendum 1's table); an empty `ablation_config` is F.
- **A complete scenario** has a scored run under every configuration that ran. A scenario
  without one is removed from every experiment (Addendum 3: *a second [discard] removes the
  scenario from every configuration*) and its runs are tabled apart, as a supplement.
- **Paired differences** count an abstention, a gate and a missing verdict as 0 on both sides,
  as the headline did, so every complete scenario enters every pair.
- **Cost and time are also read on the scenarios where neither arm was gated.** A gated run
  spends almost nothing and reports at once, so an arm gated more often looks cheaper and faster
  for a reason that is not its dimension.
- **Each experiment's bootstrap starts from its own `random.Random(20261011)`** (the queue's
  seed), so one report's intervals do not depend on how many reports precede it.
- **The MDE is the harness's formula** (`evalharness.variance.mde`), copied here so this file
  stays standard library; `tests/test_t73_v2_reports.py` holds the two equal.
"""

from __future__ import annotations

import csv
import json
import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analysis_headline_v2 as h

SWEEP = "t73-v2"
SEED = 20261011
CONFIGS = ("F", "E1", "E3", "E4", "E5", "E6", "E7", "E8", "E9")
EXPERIMENTS = ("E1", "E3", "E4", "E5", "E6", "E7", "E8", "E9")
NAMES = {
    "F": "control",
    "E1": "single agent (B1) vs parallel specialists",
    "E2": "topology scoping off",
    "E3": "raw context vs evidence compression",
    "E4": "specialists on Claude Sonnet 4.6",
    "E5": "retrieval off",
    "E6": "dense-only retrieval",
    "E7": "cross-encoder rerank on",
    "E8": "temporal scoping off (7-day windows)",
    "E9": "push-everything briefings",
}
SWITCH = {
    "no_corpus": "E5",
    "role_models": "E4",
    "rerank_model": "E7",
    "retrieval_mode": "E6",
    "evidence_mode": "E3",
    "briefing_mode": "E9",
    "default_lookback_seconds": "E8",
    "hop_radius": "E2",
}
SLUG = {
    "E1": "single-agent",
    "E2": "topology-scoping",
    "E3": "raw-context",
    "E4": "model-tier",
    "E5": "retrieval-off",
    "E6": "dense-only",
    "E7": "rerank",
    "E8": "temporal-scoping",
    "E9": "push-briefings",
}
DATE = "2026-10-15"


def report_name(e: str) -> str:
    return f"ABLATION-{DATE}-{e}-{SLUG[e]}.md"


REGISTERED_N = 12
RETRIEVALS = Path(__file__).resolve().parents[2] / "docs/evidence/t7.3/retrievals-t73-v2.tsv"
RRF_SINGLE_ARM_MAX = 1 / 61  # `context.store.RRF_K` is 60: one arm's best rank scores 1/61
RADII = Path(__file__).resolve().parents[2] / "docs/evidence/t7.3/trial/e2-radius-by-scenario.tsv"

# The registration's cost-and-time predictions, as (low, high) bounds on E's total cost relative
# to F's, in percent; None is an open end. E1's "30-70 % less" is (-70, -30).
COST_PREDICTION = {
    "E1": ((-70, -30), "B1 costs 30-70 % less"),
    "E3": ((15, None), "cost at least 15 % higher"),
    "E4": ((-45, -20), "cost 20-45 % lower"),
    "E5": ((-15, 15), "cost within +-15 %"),
    "E6": ((-10, 10), "cost within +-10 %"),
    "E7": ((None, 15), "cost within +15 % (read as: no more than 15 % higher)"),
    "E8": ((10, None), "cost at least 10 % higher"),
    "E9": ((20, None), "cost at least 20 % higher"),
}

Z_ALPHA = 1.959963985
Z_BETA = 0.841621234


def mde(n: int, p: float = 0.5, rho: float = 0.8, r: int = 1) -> float:
    """`evalharness.variance.mde`, verbatim in arithmetic."""
    return (Z_ALPHA + Z_BETA) * math.sqrt(2 * p * (1 - p) * (1 - rho) / (n * r))


# --- reading ---------------------------------------------------------------------------------


def config_of(manifest: dict) -> str:
    if manifest.get("baseline"):
        return "E1" if str(manifest["baseline"]).lower() == "b1" else str(manifest["baseline"])
    switches = manifest.get("ablation_config") or {}
    found = {SWITCH[k] for k in switches if k in SWITCH}
    if len(found) > 1:
        raise SystemExit(f"{manifest.get('run_id')}: more than one switch set: {sorted(found)}")
    return found.pop() if found else "F"


def read(root: Path, sweep: str) -> list[dict]:
    runs = []
    for path in sorted(root.glob("*/manifest.json")):
        try:
            manifest = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        meta = manifest.get("sweep") or {}
        if meta.get("id") != sweep:
            continue
        runs.append(
            {
                "dir": path.parent,
                "m": manifest,
                "slot": meta.get("slot"),
                "arm": config_of(manifest) if sweep == SWEEP else h.arm_of(manifest),
                "scenario": manifest.get("scenario_id"),
                "split": manifest.get("split"),
                "outcome": h.outcome_of(manifest),
            }
        )
    return runs


def gather(root: Path) -> dict:
    runs = read(root, SWEEP)
    slots = h.scored_by_slot(runs)
    by_scenario: dict[str, dict[str, dict]] = defaultdict(dict)
    meta: dict[tuple[str, str], dict] = {}
    for run in slots.values():
        by_scenario[run["scenario"]][run["arm"]] = h.facts(run)
        meta[(run["scenario"], run["arm"])] = {
            "slot": run["slot"],
            "trajectory_id": (run["m"].get("score") or {}).get("trajectory_id"),
            "git_sha": (run["m"].get("recorder") or {}).get("git_sha"),
        }
    seen = sorted({r["scenario"] for r in runs})
    complete = sorted(s for s in by_scenario if set(by_scenario[s]) == set(CONFIGS))
    headline_f = {}
    for run in h.scored_by_slot(read(root, h.SWEEP)).values():
        if run["arm"] == "F" and run["scenario"] in complete:
            headline_f[run["scenario"]] = h.facts(run)
    return {
        "runs": runs,
        "slots": slots,
        "table": by_scenario,
        "meta": meta,
        "complete": complete,
        "removed": sorted(set(seen) - set(complete)),
        "headline_f": headline_f,
    }


# --- small statistics ------------------------------------------------------------------------


def right(row: dict, axis: str) -> int:
    return int(row[axis]["right"])


def paired_points(table, scenarios, a, b, axis, seed=SEED):
    """Mean of (b right - a right) over scenarios, in points, with a bootstrap interval."""
    rng = random.Random(seed)

    def mean_of(sample):
        return statistics.mean(right(table[s][b], axis) - right(table[s][a], axis) for s in sample)

    lo, hi = h.bootstrap(scenarios, mean_of, rng)
    return 100 * mean_of(scenarios), 100 * lo, 100 * hi


def relative_cost(table, scenarios, a, b, seed=SEED):
    """(sum b / sum a - 1) in percent, with a bootstrap interval, and the mean paired $ gap."""
    rng = random.Random(seed)

    def rel(sample):
        base = sum(table[s][a]["billed"] for s in sample)
        return None if base == 0 else sum(table[s][b]["billed"] for s in sample) / base - 1

    lo, hi = h.bootstrap(scenarios, rel, rng)
    gap = statistics.mean(table[s][b]["billed"] - table[s][a]["billed"] for s in scenarios)
    value = rel(scenarios)
    return (math.nan if value is None else 100 * value), 100 * lo, 100 * hi, gap


def time_gap(table, scenarios, a, b, seed=SEED):
    """Mean paired seconds-to-report gap (b - a), with a bootstrap interval."""
    usable = [
        s
        for s in scenarios
        if table[s][a]["report_s"] is not None and table[s][b]["report_s"] is not None
    ]
    if not usable:
        return math.nan, math.nan, math.nan, 0
    rng = random.Random(seed)

    def gap(sample):
        return statistics.mean(table[s][b]["report_s"] - table[s][a]["report_s"] for s in sample)

    lo, hi = h.bootstrap(usable, gap, rng)
    return gap(usable), lo, hi, len(usable)


def verdict(points: float, threshold: float, lo: float, hi: float) -> str:
    """The plan's rule on the point estimate, and whether the interval clears zero beside it: a
    difference past the MDE whose interval still reaches zero is said to be so."""
    if abs(points) < threshold:
        return "no measurable effect at this catalog size"
    clear = lo > 0 or hi < 0
    return (
        "beyond the MDE; the interval excludes zero"
        if clear
        else ("beyond the MDE, but the interval reaches zero")
    )


def accuracy_cell(rows: list[dict], axis: str) -> str:
    k, n = h.ratio(rows, axis)
    return f"{k}/{n} = {h.pct(k / n if n else math.nan)}"


def within(value: float, bounds: tuple) -> bool:
    low, high = bounds
    return (low is None or value >= low) and (high is None or value <= high)


def retrieval_rows(g: dict) -> list[str]:
    """E6's registered extra reading (the trial's Addendum 8): for each scenario, how many of the
    hits F retrieved were ranked by *both* arms of the hybrid (a fused score above one arm's best,
    1/61), and how many documents F and E6 retrieved in common. Read from the trajectory store's
    export, committed beside the trial's evidence."""
    if not RETRIEVALS.exists():
        pending = f"*The per-hit reading is pending: `{RETRIEVALS.name}` is not in the tree yet.*"
        return [pending, ""]
    by_trajectory: dict[str, list[tuple[list[str], list[float]]]] = defaultdict(list)
    with RETRIEVALS.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            by_trajectory[row["trajectory_id"]].append(
                (json.loads(row["returned"]), json.loads(row["scores"]))
            )
    out = [
        "**Which hybrid arm found each hit** (the trial's registered reading), from "
        f"`docs/evidence/t7.3/{RETRIEVALS.name}` (the trajectory store's retrieval rows for this "
        "batch). A fused score above 1/61 means both the dense and the text arm ranked the chunk.",
        "",
        "| scenario | F's hits | of them ranked by both arms | E6's hits | documents F and E6 "
        "both retrieved |",
        "|---|---|---|---|---|",
    ]
    totals = [0, 0, 0]
    for s in g["complete"]:
        f_id = g["meta"][(s, "F")]["trajectory_id"]
        e_id = g["meta"][(s, "E6")]["trajectory_id"]
        f_rows = by_trajectory.get(f_id or "", [])
        e_rows = by_trajectory.get(e_id or "", [])
        if not f_rows and not e_rows:
            out.append(f"| `{s}` | no retrieval (gated) | | | |")
            continue
        f_scores = [x for _, scores in f_rows for x in scores]
        both = sum(x > RRF_SINGLE_ARM_MAX + 1e-12 for x in f_scores)
        e_hits = sum(len(docs) for docs, _ in e_rows)
        common = {d for docs, _ in f_rows for d in docs} & {d for docs, _ in e_rows for d in docs}
        totals[0] += len(f_scores)
        totals[1] += both
        totals[2] += e_hits
        out.append(f"| `{s}` | {len(f_scores)} | {both} | {e_hits} | {len(common)} |")
    out.append(f"| **all** | {totals[0]} | {totals[1]} | {totals[2]} | |")
    out.append("")
    return out


# --- one experiment --------------------------------------------------------------------------


def experiment_block(g: dict, e: str) -> list[str]:
    table, complete = g["table"], g["complete"]
    n = len(complete)
    threshold = 100 * mde(n)
    out = [f"<!-- t73:{e}:begin -->"]
    out.append(
        f"Generated by `python3 evals/runs/analysis_t73_v2.py evals/runs --block {e}`; "
        "`tests/test_t73_v2_reports.py` fails when this block and the tree disagree."
    )
    out.append("")
    out.append(
        f"**The MDE, stated first.** Paired, 80 % power, two-sided alpha 0.05, worst case p = 0.5, "
        f"R = 1: **{threshold:.0f} points at n = {n}** with rho 0.8 (the registration's "
        f"{100 * mde(REGISTERED_N):.0f} at its n = {REGISTERED_N}; {100 * mde(n, rho=0.5):.0f} "
        "at rho 0.5). The v1 A/A floor is 10.0 points. A difference inside the MDE is *no "
        "measurable effect at this catalog size*."
    )
    out.append("")
    out.append(f"{n} complete scenarios, R = 1, run in one shuffled queue with every other arm.")
    out.append("")
    out.append(
        "| config | fault class | coverage | culprit service | fix class | gated "
        "| median billed $ | median s to report |"
    )
    out.append("|---|---|---|---|---|---|---|---|")
    for arm in ("F", e):
        rows = [table[s][arm] for s in complete]
        abst = sum(r["fault_class"]["abstained"] for r in rows)
        times = [r["report_s"] for r in rows if r["report_s"] is not None]
        out.append(
            f"| {arm} | {accuracy_cell(rows, 'fault_class')} | {n - abst}/{n} | "
            f"{accuracy_cell(rows, 'service')} | {accuracy_cell(rows, 'fix_class')} | "
            f"{sum(r['gated'] for r in rows)} | "
            f"{statistics.median(r['billed'] for r in rows):.2f} | "
            f"{statistics.median(times):.0f} |"
        )
    out.append("")
    out.append(f"**Paired, {e} - F, over the {n}** (bootstrap 10,000, seed {SEED}):")
    out.append("")
    out.append("| measure | difference | 95 % interval | reading |")
    out.append("|---|---|---|---|")
    for axis, label in (("fault_class", "fault class"), ("service", "culprit service")):
        mean, lo, hi = paired_points(table, complete, "F", e, axis)
        out.append(
            f"| {label} | {mean:+.0f} pts | {lo:+.0f} to {hi:+.0f} | "
            f"{verdict(mean, threshold, lo, hi)} |"
        )
    rel, lo, hi, gap = relative_cost(table, complete, "F", e)
    out.append(f"| total cost | {rel:+.0f} % ({gap:+.2f} $ a run) | {lo:+.0f} % to {hi:+.0f} % | |")
    t, tlo, thi, tn = time_gap(table, complete, "F", e)
    out.append(f"| time to report | {t:+.0f} s | {tlo:+.0f} to {thi:+.0f} s | n = {tn} |")
    ungated = [s for s in complete if not table[s]["F"]["gated"] and not table[s][e]["gated"]]
    if len(ungated) < n:
        rel, lo, hi, gap = relative_cost(table, ungated, "F", e)
        out.append(
            f"| total cost, neither gated (n = {len(ungated)}) | {rel:+.0f} % ({gap:+.2f} $ a run) "
            f"| {lo:+.0f} % to {hi:+.0f} % | |"
        )
        t, tlo, thi, tn = time_gap(table, ungated, "F", e)
        out.append(
            f"| time to report, neither gated (n = {tn}) | {t:+.0f} s | "
            f"{tlo:+.0f} to {thi:+.0f} s | |"
        )
    out.append("")
    if e == "E1":
        f_ungated = [s for s in complete if not table[s]["F"]["gated"]]
        out.append(
            f"**Read with F's gated runs set aside** (B1 is never gated; the registration asks for "
            f"this reading), n = {len(f_ungated)}, MDE {100 * mde(len(f_ungated)):.0f}:"
        )
        out.append("")
        out.append("| measure | difference | 95 % interval | reading |")
        out.append("|---|---|---|---|")
        t2 = 100 * mde(len(f_ungated))
        for axis, label in (("fault_class", "fault class"), ("service", "culprit service")):
            mean, lo, hi = paired_points(table, f_ungated, "F", e, axis)
            out.append(
                f"| {label} | {mean:+.0f} pts | {lo:+.0f} to {hi:+.0f} | "
                f"{verdict(mean, t2, lo, hi)} |"
            )
        out.append("")
    bounds, words = COST_PREDICTION[e]
    rel_all = relative_cost(table, complete, "F", e)[0]
    rel_ungated = relative_cost(table, ungated, "F", e)[0]

    def held(value: float) -> str:
        return "held" if within(value, bounds) else "did not hold"

    out.append(
        f"**The registered prediction**: fault class and service inside the MDE; {words}. "
        f"Measured: total cost {rel_all:+.0f} % on all {n} (**{held(rel_all)}**), "
        f"{rel_ungated:+.0f} % on the {len(ungated)} where neither was gated "
        f"(**{held(rel_ungated)}**)."
    )
    out.append("")
    other = g["headline_f"]
    both = [s for s in complete if s in other]
    merged = {s: {"F": table[s]["F"], "H": other[s]} for s in both}
    aa_mean, aa_lo, aa_hi = paired_points(merged, both, "H", "F", "fault_class")
    out.append(
        f"**The A/A reading**: this batch's F against the headline run's F on the same {len(both)} "
        f"scenarios differs by {aa_mean:+.0f} points on fault class "
        f"({aa_lo:+.0f} to {aa_hi:+.0f}), "
        f"{verdict(aa_mean, 100 * mde(len(both)), aa_lo, aa_hi)}; "
        + (
            "the instrument did not drift past what this size can see"
            if abs(aa_mean) < 100 * mde(len(both))
            else "**the instrument may have drifted, and this experiment is read in that light**"
        )
        + " (`docs/ABLATIONS.md`, the A/A table, scenario by scenario)."
    )
    out.append("")
    if e == "E6":
        out += retrieval_rows(g)
    out.append("**Scenario by scenario** (fault class / culprit service):")
    out.append("")
    out.append("| scenario | class | F | " + e + " |")
    out.append("|---|---|---|---|")
    for s in complete:
        f_row, e_row = table[s]["F"], table[s][e]
        out.append(
            f"| `{s}` | {f_row['fault_class']['truth']} | "
            f"{h.mark(f_row, 'fault_class')} / {h.mark(f_row, 'service')} | "
            f"{h.mark(e_row, 'fault_class')} / {h.mark(e_row, 'service')} |"
        )
    out.append("")
    out.append(f"<!-- t73:{e}:end -->")
    return out


def e2_block() -> list[str]:
    rows = list(csv.DictReader(RADII.open(), delimiter="\t"))
    differ = [r for r in rows if r["radius_2"] != r["radius_99"]]
    out = ["<!-- t73:E2:begin -->"]
    out.append(
        "Generated by `python3 evals/runs/analysis_t73_v2.py evals/runs --block E2` from "
        "`docs/evidence/t7.3/trial/e2-radius-by-scenario.tsv`; "
        "`tests/test_t73_v2_reports.py` fails when this block and the file disagree."
    )
    out.append("")
    out.append("| scenario | the page (alerting services) | blast radius at 2 hops | at 99 hops |")
    out.append("|---|---|---|---|")
    for r in rows:
        out.append(f"| `{r['scenario']}` | {r['page']} | {r['radius_2']} | {r['radius_99']} |")
    out.append("")
    out.append(
        f"**{len(differ)} of {len(rows)}** scenarios have a different blast radius at 99 hops: "
        + (", ".join(f"`{r['scenario']}` ({r['radius_2']} to {r['radius_99']})" for r in differ))
        + "."
    )
    out.append("")
    out.append("<!-- t73:E2:end -->")
    return out


# --- the A/A check, the record, the supplement, the overview ---------------------------------


def aa_block(g: dict) -> list[str]:
    table, complete, other = g["table"], g["complete"], g["headline_f"]
    both = [s for s in complete if s in other]
    merged = {s: {"F": table[s]["F"], "H": other[s]} for s in both}
    threshold = 100 * mde(len(both))
    out = ["<!-- t73:aa:begin -->"]
    out.append(
        f"F in this batch against F in the headline run (`sweep.id` `headline-v2`) on the "
        f"{len(both)} complete scenarios: the same configuration twice, nine days apart. "
        f"MDE {threshold:.0f} points at n = {len(both)}."
    )
    out.append("")
    out.append(
        "| measure | headline F | this batch's F | batch - headline | 95 % interval | reading |"
    )
    out.append("|---|---|---|---|---|---|")
    for axis, label in (("fault_class", "fault class"), ("service", "culprit service")):
        mean, lo, hi = paired_points(merged, both, "H", "F", axis)
        out.append(
            f"| {label} | {accuracy_cell([other[s] for s in both], axis)} | "
            f"{accuracy_cell([table[s]['F'] for s in both], axis)} | {mean:+.0f} pts | "
            f"{lo:+.0f} to {hi:+.0f} | {verdict(mean, threshold, lo, hi)} |"
        )
    out.append("")
    agree = sum(
        h.mark(table[s]["F"], "fault_class") == h.mark(other[s], "fault_class") for s in both
    )
    out.append(
        f"Same mark on fault class (right, wrong with the same label, abstained, gated) on "
        f"**{agree} of {len(both)}** scenarios."
    )
    out.append("")
    out.append("| scenario | headline F | this batch's F |")
    out.append("|---|---|---|")
    for s in both:
        out.append(
            f"| `{s}` | {h.mark(other[s], 'fault_class')} / {h.mark(other[s], 'service')} | "
            f"{h.mark(table[s]['F'], 'fault_class')} / {h.mark(table[s]['F'], 'service')} |"
        )
    out.append("")
    out.append("<!-- t73:aa:end -->")
    return out


def record_block(g: dict) -> list[str]:
    runs, table, complete, meta = g["runs"], g["table"], g["complete"], g["meta"]
    out = ["<!-- t73:record:begin -->"]
    outcomes = Counter(r["outcome"] for r in runs)
    started = len(runs)
    discards = [r for r in runs if r["outcome"] == "discarded"]
    out.append(
        f"Runs read: **{started}** (`sweep.id` `{SWEEP}`), "
        f"outcomes {dict(sorted(outcomes.items()))}; "
        f"**{len(g['slots'])} of 99 slots** have a scored run; discards "
        f"{len(discards)}/{started} = {h.pct(len(discards) / started)} of started."
    )
    out.append("")
    out.append("| slot | config | scenario | discard reason |")
    out.append("|---|---|---|---|")
    for r in sorted(discards, key=lambda r: (r["slot"], r["dir"].name)):
        reason = (r["m"].get("discarded") or {}).get("reason")
        out.append(f"| {r['slot']} | {r['arm']} | `{r['scenario']}` | {reason} |")
    out.append("")
    out.append(
        "**Removed from every experiment**: "
        + (", ".join(f"`{s}`" for s in g["removed"]) or "none")
        + " - a configuration without a scored run (two discards)."
    )
    out.append("")
    out.append("**Gated by triage, per configuration and scenario** (E1 is never gated):")
    out.append("")
    out.append("| scenario | " + " | ".join(CONFIGS) + " |")
    out.append("|---|" + "---|" * len(CONFIGS))
    gated_scenarios = sorted(
        s for s in table if any(table[s].get(a, {}).get("gated") for a in CONFIGS)
    )
    for s in gated_scenarios:
        cells = [
            "gated" if table[s].get(a, {}).get("gated") else ("-" if a in table[s] else "n/a")
            for a in CONFIGS
        ]
        out.append(f"| `{s}` | " + " | ".join(cells) + " |")
    totals = [sum(bool(table[s].get(a, {}).get("gated")) for s in complete) for a in CONFIGS]
    out.append("| **gated of the complete** | " + " | ".join(str(t) for t in totals) + " |")
    out.append("")
    shas: dict[str, list[int]] = defaultdict(list)
    for (_, _), info in meta.items():
        shas[str(info["git_sha"])[:8]].append(info["slot"])
    out.append(
        "**The harness's code version per scored slot**: "
        + "; ".join(
            f"`{sha}` slots {min(slots)}-{max(slots)} ({len(slots)})"
            for sha, slots in sorted(shas.items(), key=lambda kv: min(kv[1]))
        )
        + ". The change between them (#670) is in the disk-fill revert, which runs after scoring."
    )
    out.append("")
    stamps = Counter(table[s][a]["stamp"] for s in table for a in table[s])
    worlds = Counter(table[s][a]["world"] for s in table for a in table[s])
    out.append(
        f"**Stamps**: {len(stamps)} distinct ("
        + ", ".join(f"`{p}` / `{c}` x{k}" for (p, c), k in stamps.items())
        + f"); distinct world digests {len(worlds)}."
    )
    out.append("")
    out.append("<!-- t73:record:end -->")
    return out


def supplement_block(g: dict) -> list[str]:
    table = g["table"]
    out = ["<!-- t73:supplement:begin -->"]
    out.append(
        "The removed scenarios' scored runs, **outside every comparison**: run as the "
        "registration's fixed queue required, kept because they happened, and never in a "
        "difference above."
    )
    out.append("")
    out.append("| scenario | config | fault class | culprit service | billed $ |")
    out.append("|---|---|---|---|---|")
    for s in g["removed"]:
        for a in CONFIGS:
            row = table.get(s, {}).get(a)
            if row is None:
                out.append(f"| `{s}` | {a} | no scored run | | |")
                continue
            out.append(
                f"| `{s}` | {a} | {h.mark(row, 'fault_class')} | {h.mark(row, 'service')} | "
                f"{row['billed']:.2f} |"
            )
    out.append("")
    out.append("<!-- t73:supplement:end -->")
    return out


def overview_block(g: dict) -> list[str]:
    table, complete = g["table"], g["complete"]
    n = len(complete)
    threshold = 100 * mde(n)
    out = ["<!-- t73:overview:begin -->"]
    out.append(
        "Generated by `python3 evals/runs/analysis_t73_v2.py evals/runs --block overview`. "
        f"Each experiment is E - F, paired over the same {n} dev scenarios, R = 1; MDE "
        f"**{threshold:.0f} points** (rho 0.8). Cost is E's total over F's, on the scenarios "
        "where neither was gated."
    )
    out.append("")
    f_gated = sum(table[s]["F"]["gated"] for s in complete)
    out.append(
        "| experiment | fault class | culprit service | cost | time to report "
        f"| gated (F {f_gated}) | report |"
    )
    out.append("|---|---|---|---|---|---|---|")
    for e in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"):
        link = f"[{e}](../evals/runs/{report_name(e)})"
        if e == "E2":
            out.append(
                f"| E2 {NAMES['E2']} | not run | not run | - | - | - | {link}: the radius "
                "differs on 1 of 12 |"
            )
            continue
        cells = []
        for axis in ("fault_class", "service"):
            mean, lo, hi = paired_points(table, complete, "F", e, axis)
            mark = "" if abs(mean) < threshold else " **beyond MDE**"
            cells.append(f"{mean:+.0f} ({lo:+.0f} to {hi:+.0f}){mark}")
        ungated = [s for s in complete if not table[s]["F"]["gated"] and not table[s][e]["gated"]]
        rel, lo, hi, _ = relative_cost(table, ungated, "F", e)
        t, _, _, _ = time_gap(table, ungated, "F", e)
        gated = sum(table[s][e]["gated"] for s in complete)
        out.append(
            f"| {e} {NAMES[e]} | {cells[0]} | {cells[1]} | {rel:+.0f} % ({lo:+.0f} to {hi:+.0f}) "
            f"| {t:+.0f} s | {gated} | {link} |"
        )
    out.append("")
    out.append("<!-- t73:overview:end -->")
    return out


BLOCKS = {
    **{e: (lambda g, e=e: experiment_block(g, e)) for e in EXPERIMENTS},
    "E2": lambda g: e2_block(),
    "aa": aa_block,
    "record": record_block,
    "supplement": supplement_block,
    "overview": overview_block,
}


NEGATIVE_ZERO = re.compile(r"(?<![\w.])-0(?![\w.])")


def tidy(lines: list[str]) -> list[str]:
    """A rounded -0.3 prints as "-0"; it is shown as "+0" so a null reads as one."""
    return [NEGATIVE_ZERO.sub("+0", line) for line in lines]


def render(g: dict, name: str) -> list[str]:
    return tidy(BLOCKS[name](g))


def main(root: Path, block: str | None) -> None:
    g = gather(root)
    if block:
        if block not in BLOCKS:
            raise SystemExit(f"unknown block {block!r}; one of {sorted(BLOCKS)}")
        print("\n".join(render(g, block)))
        return
    out = ["# T7.3 on v2 - computed tables", ""]
    for name in ("record", "overview", "aa", "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"):
        out += [f"## {name}", "", *render(g, name), ""]
    out += ["## supplement", "", *render(g, "supplement"), ""]
    print("\n".join(out))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    chosen = None
    if "--block" in sys.argv:
        chosen = sys.argv[sys.argv.index("--block") + 1]
        args = [a for a in args if a != chosen]
    main(Path(args[0] if args else "evals/runs"), chosen)
