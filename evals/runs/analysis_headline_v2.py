"""The headline run's analysis, exactly as `PREREGISTRATION-headline-v2.md` fixed it.

Standard library only, so anyone with Python 3.10+ and this repository's `evals/runs/` can
reproduce every figure in `HEADLINE-v2.md`:

    python3 evals/runs/analysis_headline_v2.py evals/runs > /tmp/headline.md

What it reads: every `evals/runs/*/manifest.json` whose `sweep.id` is `headline-v2`, plus the
`investigate.txt` beside a Faultline run (for the page's severity on a gated run). Nothing else.

Decisions the registration left open, made here once and printed in the output:

- **The scored run of a slot** is the one run of that slot with no `refused`, `discarded` or
  `invalid` mark. A slot with two such runs is an error, not a choice.
- **A removed scenario** is one where any arm has no scored run (*A scenario that will not run*).
  Its scored arms are listed and left out of every denominator.
- **Paired differences** count an abstention, a gate and a missing verdict as 0 (not right) on
  both sides, so every scenario contributes to every pair.
- **The bootstrap seed** is the queue's, 20261006.
"""

from __future__ import annotations

import json
import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

SWEEP = "headline-v2"
ARMS = ("F", "B0", "B1", "B2")
AXES = ("fault_class", "service", "fix_class")
SEED = 20261006
RESAMPLES = 10_000
BILLED = 1.26
MDE = {"holdout": 28, "dev": 16, "all": 14}  # the registration's table, at rho 0.8


# --- reading ---------------------------------------------------------------------------------


def arm_of(manifest: dict) -> str:
    base = manifest.get("baseline")
    return "F" if not base else str(base).upper()


def outlived_its_budget(manifest: dict) -> bool:
    """Q33's reading, as `evalharness.evaldb.outlived_its_budget` makes it: a scored run whose
    investigation ran longer than the wall clock its own manifest declares is `invalid`. The
    first cut of this script did not apply it and counted slot 127 (624 s against 600 s) as
    scored; `HEADLINE-2026-10-11-v2.md` §7 and Addendum 6 record the correction."""
    latency = ((manifest.get("metrics") or {}).get("latency") or {}).get("investigation_seconds")
    declared = (manifest.get("budget") or {}).get("wall_clock_seconds")
    if latency is None or not declared:
        return False
    return float(latency) > float(declared)


def outcome_of(manifest: dict) -> str:
    for mark in ("refused", "discarded", "invalid"):
        if manifest.get(mark):
            return mark
    return "invalid" if outlived_its_budget(manifest) else "scored"


def severity_of(run_dir: Path) -> str | None:
    path = run_dir / "investigate.txt"
    if not path.exists():
        return None
    match = re.search(r"^triage: .*?severity (\w+)", path.read_text(errors="replace"), re.M)
    return match.group(1) if match else None


def read(root: Path) -> list[dict]:
    runs = []
    for path in sorted(root.glob("*/manifest.json")):
        try:
            manifest = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        sweep = manifest.get("sweep") or {}
        if sweep.get("id") != SWEEP:
            continue
        runs.append(
            {
                "dir": path.parent,
                "m": manifest,
                "slot": sweep.get("slot"),
                "arm": arm_of(manifest),
                "scenario": manifest.get("scenario_id"),
                "split": manifest.get("split"),
                "outcome": outcome_of(manifest),
            }
        )
    return runs


def scored_by_slot(runs: list[dict]) -> dict[int, dict]:
    """The one usable run of each slot. An `invalid` run is a run that happened and may not be
    used (Q33); it is listed under *Removed* with its reason, never scored."""
    chosen: dict[int, dict] = {}
    for run in runs:
        if run["outcome"] != "scored":
            continue
        if run["slot"] in chosen:
            raise SystemExit(f"slot {run['slot']} has two scored runs: {run['dir'].name}")
        chosen[run["slot"]] = run
    return chosen


# --- one run's facts -------------------------------------------------------------------------


def facts(run: dict) -> dict:
    m = run["m"]
    score = m.get("score") or {}
    gated = bool(m.get("gated"))
    out: dict = {"gated": gated, "scenario": run["scenario"], "arm": run["arm"]}
    for axis in AXES:
        label = score.get(axis) or {}
        returned = label.get("returned")
        abstained = bool(label.get("abstained"))
        no_verdict = not gated and not abstained and returned in (None, "")
        out[axis] = {
            "truth": label.get("truth"),
            "returned": returned,
            "right": bool(label.get("correct")),
            "by_alternative": bool(label.get("correct_by_alternative")),
            "abstained": abstained,
            "no_verdict": no_verdict,
        }
    cost = float(score.get("cost_usd") or 0.0)
    out["billed"] = round(cost * BILLED, 4)
    latency = ((m.get("metrics") or {}).get("latency") or {}).get("investigation_seconds")
    out["report_s"] = latency
    try:
        start = datetime.fromisoformat(m["started_at"])
        end = datetime.fromisoformat(m["finished_at"])
        out["wall_min"] = (end - start).total_seconds() / 60
    except (KeyError, TypeError, ValueError):
        out["wall_min"] = None
    judge = m.get("judge") or {}
    out["judge"] = judge.get("root_cause_agreement") if judge.get("scored") else None
    out["severity"] = severity_of(run["dir"]) if run["arm"] == "F" else None
    out["gate_reason"] = (m.get("gated") or {}).get("reasoning")
    out["adversarial"] = (m.get("adversarial") or {}).get("outcome")
    # Prediction 10: the stamp (one per arm by design) and the world digests. The tool layer's
    # git sha is reported apart: it moved once, by Addendum 4's fix, and the code it names is
    # recorded rather than frozen.
    out["stamp"] = (
        score.get("runtime_version"),
        (m.get("freeze") or {}).get("world", {}).get("capability_version"),
    )
    out["world"] = json.dumps(
        {k: v for k, v in ((m.get("freeze") or {}).get("world") or {}).items()}, sort_keys=True
    )
    out["git_sha"] = ((m.get("freeze") or {}).get("tool_layer") or {}).get("git_sha")
    return out


# --- statistics ------------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (centre - half, centre + half)


def ratio(rows: list[dict], axis: str) -> tuple[int, int]:
    """(right, counted): counted = answered + gated + no verdict, i.e. everything not abstained."""
    counted = [r for r in rows if not r[axis]["abstained"]]
    return sum(r[axis]["right"] for r in counted), len(counted)


def bootstrap(scenarios: list[str], stat, rng: random.Random) -> tuple[float, float]:
    values = []
    for _ in range(RESAMPLES):
        sample = [rng.choice(scenarios) for _ in scenarios]
        value = stat(sample)
        if value is not None:
            values.append(value)
    values.sort()
    if not values:
        return (math.nan, math.nan)
    return (values[int(0.025 * len(values))], values[int(0.975 * len(values)) - 1])


def pct(x: float) -> str:
    return "n/a" if x != x else f"{100 * x:.0f}%"


# --- the tables ------------------------------------------------------------------------------


def arm_table(table: dict, scenarios: list[str], title: str, rng: random.Random) -> list[str]:
    lines = [f"### {title}", "", f"{len(scenarios)} scenarios.", ""]
    lines.append(
        "| arm | fault class | coverage | culprit service | fix class | gated | median billed $ "
        "| median s to report |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for arm in ARMS:
        rows = [table[s][arm] for s in scenarios]
        cells = []
        for axis in AXES:
            k, n = ratio(rows, axis)
            lo, hi = wilson(k, n)

            def stat(sample, axis=axis, arm=arm):
                picked = [table[s][arm] for s in sample]
                kk, nn = ratio(picked, axis)
                return kk / nn if nn else None

            blo, bhi = bootstrap(scenarios, stat, rng)
            cells.append(
                f"{k}/{n} = {pct(k / n if n else math.nan)} "
                f"(boot {pct(blo)}-{pct(bhi)}; Wilson {pct(lo)}-{pct(hi)})"
            )
        abst = sum(r["fault_class"]["abstained"] for r in rows)
        coverage = f"{len(rows) - abst}/{len(rows)}"
        gated = sum(r["gated"] for r in rows)
        costs = [r["billed"] for r in rows]
        times = [r["report_s"] for r in rows if r["report_s"] is not None]
        med_t = f"{statistics.median(times):.0f}" if times else "n/a"
        lines.append(
            f"| {arm} | {cells[0]} | {coverage} | {cells[1]} | {cells[2]} | "
            f"{gated if arm == 'F' else '-'} | {statistics.median(costs):.2f} | {med_t} |"
        )
    return [*lines, ""]


def paired(table: dict, scenarios: list[str], title: str, rng: random.Random, mde: int):
    lines = [f"### Paired differences, {title} (MDE {mde} points)", ""]
    lines.append("| pair | fault class | culprit service |")
    lines.append("|---|---|---|")
    results = {}
    for other in ("B0", "B1", "B2"):
        cells = []
        for axis in ("fault_class", "service"):

            def diff(s, axis=axis, other=other):
                return int(table[s]["F"][axis]["right"]) - int(table[s][other][axis]["right"])

            mean = statistics.mean(diff(s) for s in scenarios)
            lo, hi = bootstrap(
                scenarios, lambda sample: statistics.mean(diff(s) for s in sample), rng
            )
            results[(other, axis)] = (mean, lo, hi)
            cells.append(f"{100 * mean:+.0f} pts ({100 * lo:+.0f} to {100 * hi:+.0f})")
        lines.append(f"| F - {other} | {cells[0]} | {cells[1]} |")
    return [*lines, ""], results


def mark(row: dict, axis: str) -> str:
    if row["gated"]:
        return "gated"
    label = row[axis]
    if label["abstained"]:
        return "abstained"
    if label["no_verdict"]:
        return "no verdict"
    return "right" if label["right"] else f"wrong ({label['returned']})"


def gather(root: Path) -> dict:
    runs = read(root)
    slots = scored_by_slot(runs)
    rows_by_scenario: dict[str, dict[str, dict]] = defaultdict(dict)
    split_of: dict[str, str] = {}
    for run in slots.values():
        rows_by_scenario[run["scenario"]][run["arm"]] = facts(run)
        split_of[run["scenario"]] = run["split"]
    scenarios_seen = sorted({r["scenario"] for r in runs})
    complete = sorted(s for s in rows_by_scenario if set(rows_by_scenario[s]) == set(ARMS))
    return {
        "runs": runs,
        "slots": slots,
        "rows_by_scenario": rows_by_scenario,
        "split_of": split_of,
        "complete": complete,
        "removed": sorted(set(scenarios_seen) - set(complete)),
        "holdout": [s for s in complete if split_of[s] == "holdout"],
        "dev": [s for s in complete if split_of[s] == "dev"],
        "table": {s: rows_by_scenario[s] for s in complete},
    }


def readme_block(root: Path) -> str:
    """README's *Results at a glance* block: the holdout headline and nothing else.

    The same rows, the same seed and the same order of draws as `main`, so the figures here are
    the report's figures. `tests/test_headline_v2_readme.py` regenerates this and compares.
    """
    g = gather(root)
    table, holdout, removed = g["table"], g["holdout"], g["removed"]
    rng = random.Random(SEED)
    out = [
        "<!-- headline-v2:begin -->",
        "Generated by `python3 evals/runs/analysis_headline_v2.py evals/runs --readme`; "
        "`tests/test_headline_v2_readme.py` fails when this block and the tree disagree. "
        f"Holdout only, R = 1, {len(holdout)} scenarios; every rate with a bootstrap interval "
        "over scenarios (10,000 resamples, seed 20261006) and a Wilson interval. "
        "A difference inside the registered 28-point MDE is *no measurable effect at this n*.",
        "",
    ]
    out += arm_table(table, holdout, "Holdout", rng)[4:]
    lines, _ = paired(table, holdout, "holdout", rng, MDE["holdout"])
    out += lines[2:]
    if removed:
        out.append(
            "Removed, an arm without a usable run (both tries failed, or the one run is "
            "`invalid` under Q33): " + ", ".join(f"`{s}`" for s in removed) + "."
        )
        out.append("")
    out.append("<!-- headline-v2:end -->")
    return "\n".join(out)


def main(root: Path) -> None:
    g = gather(root)
    runs, slots, rows_by_scenario = g["runs"], g["slots"], g["rows_by_scenario"]
    split_of, complete, removed = g["split_of"], g["complete"], g["removed"]
    holdout, dev, table = g["holdout"], g["dev"], g["table"]
    rng = random.Random(SEED)

    out = ["# Headline v2 - computed tables", ""]
    out.append(
        f"Runs read: {len(runs)} (`sweep.id` = `{SWEEP}`); scored slots {len(slots)}; "
        f"complete scenarios {len(complete)} ({len(dev)} dev, {len(holdout)} holdout)."
    )
    outcomes = Counter(r["outcome"] for r in runs)
    out.append(f"Run outcomes: {dict(sorted(outcomes.items()))}.")
    out.append("")
    out.append("**Removed** (an arm without a scored run, so out of every denominator):")
    out.append("")
    for s in removed:
        arms = sorted(rows_by_scenario.get(s, {}))
        reasons = Counter(
            str((r["m"].get("discarded") or {}).get("reason"))
            for r in runs
            if r["scenario"] == s and r["outcome"] == "discarded"
        )
        invalid = [
            f"{r['arm']} slot {r['slot']} ({r['dir'].name})"
            for r in runs
            if r["scenario"] == s and r["outcome"] == "invalid"
        ]
        out.append(
            f"- `{s}`: scored arms {arms or 'none'}; discards {dict(reasons)}; "
            f"invalid {invalid or 'none'}"
        )
    out.append("")

    out += arm_table(table, holdout, "The headline: holdout", rng)
    p_hold, d_hold = paired(table, holdout, "holdout", rng, MDE["holdout"])
    out += p_hold
    out += arm_table(table, dev, "Diagnostic: dev", rng)
    p_dev, _ = paired(table, dev, "dev", rng, MDE["dev"])
    out += p_dev
    out += arm_table(table, complete, "All complete scenarios", rng)
    p_all, d_all = paired(table, complete, "all complete scenarios", rng, MDE["all"])
    out += p_all

    out += ["### Holdout, scenario by scenario", ""]
    out.append("| scenario | class | arm | fault class | service | fix class |")
    out.append("|---|---|---|---|---|---|")
    for s in holdout:
        for arm in ARMS:
            row = table[s][arm]
            out.append(
                f"| `{s}` | {row['fault_class']['truth']} | {arm} | {mark(row, 'fault_class')} | "
                f"{mark(row, 'service')} | {mark(row, 'fix_class')} |"
            )
    out.append("")

    out += ["### By class (counts, never rates)", ""]
    out.append("| split | class | n | F | B0 | B1 | B2 |")
    out.append("|---|---|---|---|---|---|---|")
    for split, group in (("holdout", holdout), ("dev", dev)):
        by_class: dict[str, list[str]] = defaultdict(list)
        for s in group:
            by_class[table[s]["F"]["fault_class"]["truth"]].append(s)
        for cls in sorted(by_class):
            members = by_class[cls]
            cells = [f"{sum(table[s][a]['fault_class']['right'] for s in members)}" for a in ARMS]
            out.append(f"| {split} | {cls} | {len(members)} | " + " | ".join(cells) + " |")
    out.append("")

    f_rows = [table[s]["F"] for s in complete]
    out += ["### Faultline's gated runs", ""]
    for s in complete:
        row = table[s]["F"]
        if row["gated"]:
            out.append(
                f"- `{s}` ({split_of[s]}), page severity {row['severity']}: {row['gate_reason']}"
            )
    out.append("")

    out += ["### The four injection scenarios (T6.8's record, as recorded)", ""]
    for s in complete:
        if not s.startswith("v2-inj-"):
            continue
        for arm in ARMS:
            adv = table[s][arm]["adversarial"]
            out.append(f"- `{s}` {arm}: {json.dumps(adv, sort_keys=True)}")
    out.append("")

    judged = Counter(r["judge"] for r in f_rows if r["judge"])
    out.append(f"**Judge on F's narratives (non-headline, not calibrated):** {dict(judged)}")
    out.append("")

    # --- predictions -------------------------------------------------------------------------
    out += ["### Predictions, as registered", ""]

    def acc(group, arm, axis):
        k, n = ratio([table[s][arm] for s in group], axis)
        return k, n, (k / n if n else math.nan)

    k1d = acc(dev, "F", "fault_class")
    k1h = acc(holdout, "F", "fault_class")
    k2d = acc(dev, "F", "service")
    k2h = acc(holdout, "F", "service")
    gated = [r for r in f_rows if r["gated"]]
    abst = sum(r["fault_class"]["abstained"] for r in f_rows)
    order = sorted(("B0", "B1", "B2"), key=lambda a: -acc(complete, a, "fault_class")[2])
    f_b1 = d_hold[("B1", "fault_class")]
    f_b0 = d_all[("B0", "fault_class")]
    f_b2 = d_all[("B2", "fault_class")]
    med_cost = {a: statistics.median(table[s][a]["billed"] for s in complete) for a in ARMS}
    walls = [table[s][a]["wall_min"] for s in complete for a in ARMS if table[s][a]["wall_min"]]
    started = [r for r in runs if r["outcome"] in ("scored", "discarded")]
    discards = [r for r in runs if r["outcome"] == "discarded"]
    stamps = {a: {table[s][a]["stamp"] for s in complete} for a in ARMS}
    worlds = {table[s][a]["world"] for s in complete for a in ARMS}
    shas = Counter(table[s][a]["git_sha"] for s in complete for a in ARMS)
    out.append(
        f"1. F fault class: dev {k1d[0]}/{k1d[1]} = {pct(k1d[2])} (50-85), "
        f"holdout {k1h[0]}/{k1h[1]} = {pct(k1h[2])} (40-90)"
    )
    out.append(
        f"2. F service: dev {k2d[0]}/{k2d[1]} = {pct(k2d[2])} (50-80), "
        f"holdout {k2h[0]}/{k2h[1]} = {pct(k2h[2])} (40-90)"
    )
    out.append(
        f"3. gated {len(gated)} of {len(f_rows)} F runs; page severities "
        f"{sorted(r['severity'] or '?' for r in gated)} (at most 4, warning only)"
    )
    out.append(f"4. F abstained {abst}/{len(f_rows)} = {pct(abst / len(f_rows))} (at most 25%)")
    out.append(
        f"5. baselines by fault class on all complete: {' > '.join(order)} "
        f"(registered: B1 highest, B0 lowest)"
    )
    out.append(
        f"6. F - B1 holdout fault class {100 * f_b1[0]:+.0f} pts "
        f"({100 * f_b1[1]:+.0f} to {100 * f_b1[2]:+.0f}); MDE 28"
    )
    out.append(
        f"7. F - B0 {100 * f_b0[0]:+.0f} pts, F - B2 {100 * f_b2[0]:+.0f} pts on all "
        f"complete (both positive registered); MDE 14"
    )
    out.append(
        "8. median billed $ per run: "
        + ", ".join(f"{a} {med_cost[a]:.2f}" for a in ARMS)
        + " (F 0.60-1.10, B1 0.25-0.60, B2 <= 0.10, B0 0); total cap $60"
    )
    out.append(
        f"9. wall time per run median {statistics.median(walls):.1f} min "
        f"(range {min(walls):.1f}-{max(walls):.1f}; 10-18 registered); discards "
        f"{len(discards)}/{len(started)} = {pct(len(discards) / len(started))} of started "
        f"(at most 10%)"
    )
    out.append(
        "10. stamps per arm: "
        + ", ".join(f"{a} {len(stamps[a])} ({sorted(stamps[a])[0][0]})" for a in ARMS)
        + f"; distinct world digests {len(worlds)}; harness git sha {dict(shas)}"
    )
    out.append("")
    print("\n".join(out))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(args[0] if args else "evals/runs")
    if "--readme" in sys.argv:
        print(readme_block(root))
    else:
        main(root)
