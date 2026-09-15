"""`faultline-postmortem` - draft a postmortem per donor scenario, for a person to edit (T6.5).

**It writes drafts and nothing else.** The document reaches the corpus only after a person edits
it, submits it to the accept route, and commits the file - the registration's §3 in three steps,
none of which this command performs. A drafter that wrote into `evals/scenarios/artifacts/dev/`
would be *"draft for human edit, never auto-published"* with the second half removed.

So the output goes to a directory the caller names, defaulting to one outside the seeded tree.
Copying a draft into a bundle is a person's act, after they have read it.

## Why it is in the harness and not in the product

This is an authoring aid run by hand, once, against recorded runs. `faultline.agents.postmortem`
holds the role - the prompt, the contract, the guards - because that is production material the
accept route and the seeder both depend on. The walking of `evals/runs/`, the cost accounting and
the argument parsing are harness concerns, and putting them beside the role would give the product
a dependency on the eval tree.

## The budget is a hard stop, as the registration's §6 requires

`PREREGISTRATION-T6.5.md` §6 budgets **$5 for postmortem generation, ~13 calls**, inside a $55
ceiling for the whole task. `--max-usd` defaults to that $5 and stops the walk where it stands,
reporting the scenarios it did not reach. A budget revised upward mid-task is not a budget.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS = REPO_ROOT / "evals" / "runs"
DEFAULT_OUT = REPO_ROOT / "evals" / "postmortems"
"""**Outside `evals/scenarios/artifacts/dev/`, which is the seeder's one root.** A draft written
where `faultline-seed` reads would be one accepted row away from the corpus, and the gate would be
a formality between two directories rather than a person."""

MAX_USD = 5.0
"""Registration §6. Not a suggestion: `run_cli` stops at it."""


def dev_scenarios(scenarios: Path) -> set[str]:
    """Dev scenario ids, read off the catalog. §8: no holdout scenario is spent here."""
    import yaml

    found: set[str] = set()
    for path in sorted(scenarios.glob("*.yaml")):
        try:
            loaded: Any = yaml.safe_load(path.read_text())
        except Exception:
            continue
        if isinstance(loaded, dict) and str(loaded.get("split", "")) == "dev":
            found.add(path.stem)
    return found


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="faultline-postmortem",
        description=(
            "Draft one postmortem per dev scenario from its newest scored run. Writes drafts for "
            "a person to edit; nothing here accepts, seeds or publishes anything."
        ),
    )
    p.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    p.add_argument("--scenarios", type=Path, default=REPO_ROOT / "evals" / "scenarios")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--only", action="append", default=None, metavar="SCENARIO")
    p.add_argument(
        "--max-usd",
        type=float,
        default=MAX_USD,
        help="hard stop, registration §6 (default: %(default)s)",
    )
    p.add_argument(
        "--attempts",
        type=int,
        default=2,
        help="drafts per scenario before giving up; a refusal is fed back (default: %(default)s)",
    )
    p.add_argument("--dry-run", action="store_true", help="list the donors and spend nothing")
    return p


def run_cli(argv: list[str] | None = None) -> int:  # pragma: no cover - the live path
    args = parser().parse_args(argv)

    from faultline.agents.model import build_model
    from faultline.agents.postmortem import (
        PostmortemScribe,
        RecordError,
        RefusedError,
        donor_runs,
        draft_one,
        record_from_run,
    )
    from faultline.agents.settings import AgentSettings

    wanted = dev_scenarios(args.scenarios)
    if args.only:
        wanted &= set(args.only)
    donors = donor_runs(args.runs, wanted)
    if not donors:
        print("no donor run found; nothing to draft")
        return 1

    print(f"{len(donors)} donor scenario(s), newest scored run each:")
    for scenario, directory in sorted(donors.items()):
        print(f"  {scenario:34} {directory.name}")
    if args.dry_run:
        print("\n--dry-run: nothing drafted, nothing spent")
        return 0

    settings = AgentSettings()
    model = build_model(settings.model_for(PostmortemScribe.ROLE))
    args.out.mkdir(parents=True, exist_ok=True)

    prices = (settings.usd_per_mtok_in, settings.usd_per_mtok_out)
    spent = 0.0
    refused_total = 0
    written: list[str] = []
    skipped: list[tuple[str, str]] = []
    for scenario, directory in sorted(donors.items()):
        if spent >= args.max_usd:
            skipped.append((scenario, f"budget reached at ${spent:.2f}"))
            continue
        try:
            record = record_from_run(directory)
        except RecordError as unusable:
            skipped.append((scenario, str(unusable)))
            continue
        try:
            drafted = draft_one(record, model, attempts=args.attempts)
        except RefusedError as refused:
            # **A scenario that produced nothing still spent.** Q53's driver printed $0.00 while
            # a failed arm burned tokens, because it priced the verdict rather than the work.
            spent += (
                refused.tokens_in / 1_000_000 * prices[0]
                + refused.tokens_out / 1_000_000 * prices[1]
            )
            refused_total += len(refused.refusals)
            skipped.append((scenario, str(refused)))
            continue
        spent += drafted.cost_usd(*prices)
        refused_total += len(drafted.refusals)
        path = args.out / f"{scenario}.md"
        path.write_text(drafted.text)
        written.append(scenario)
        mark = f"  ({len(drafted.refusals)} refused)" if drafted.refusals else ""
        print(f"drafted {scenario}{mark} -> {path}")

    summary = {
        "donors": len(donors),
        "written": written,
        "skipped": [{"scenario": s, "why": w} for s, w in skipped],
        "guard_refusals": refused_total,
        "spend_usd": round(spent, 4),
        "max_usd": args.max_usd,
    }
    (args.out / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(f"\nwritten {len(written)}/{len(donors)}  spend ${spent:.2f} of ${args.max_usd:.2f}")
    # **Prediction 6's number, printed whichever way it went.** The registration predicts *no
    # postmortem trips the leak guard on its first draft* and says it expects that to fail; a
    # count nobody collected could not have scored it either way.
    print(f"guard refusals across all drafts: {refused_total}")
    if skipped:
        print("\nnot drafted:")
        for scenario, why in skipped:
            print(f"  {scenario}: {why}")
    print(
        "\nThese are drafts. Edit them, submit each to POST /api/v1/postmortems/<id>/accept, "
        "then commit the file into its bundle. Nothing here accepted or seeded anything."
    )
    return 0 if written else 2
