"""`faultline-render` - turn a recorded rehearsal bundle into a page a person can read.

A bundle is a directory of captures: a manifest, four or five Prometheus responses, a log
slice, the exact queries behind each file, and the narrative a responder wrote afterwards.
That layout is right for a harness and wrong for a reader, who wants to know what broke, what
paged, in what order, and what it looked like from the inside.

**Deterministic by construction.** Same bundle in, byte-identical page out: nothing here reads
the clock, the filesystem's ordering, or the environment. Every collection is sorted before it
is rendered, every time is printed as an offset from the injection rather than as a local
time, and the render carries no provenance of its own - the bundle's provenance is the
bundle's. A page that changed when it was re-rendered would be a diff nobody could review.

**No model calls and no live services.** This reads committed files and writes Markdown.

Two things it is careful about, both learned from the bundles themselves:

*Output must survive the pre-commit hooks.* `docs/bundles/` is not in the captured-evidence
exclusion, so `trailing-whitespace` and `end-of-file-fixer` rewrite anything left there. A
renderer that emitted a trailing space would be corrected on commit and would then disagree
with its own output forever. Every line is stripped and the file ends in exactly one newline.

*Captured logs are hostile by construction.* The world's services log request parameters, and
two committed captures contain ANSI escape sequences (ADR-0019 measured them rather than
supposing them). Escapes are removed before any log line reaches a page.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACTS_ROOT = REPO_ROOT / "evals" / "scenarios" / "artifacts"
DEFAULT_OUT = REPO_ROOT / "docs" / "bundles"

LOG_EXCERPT_LINES = 12
"""How much of a captured log a page shows. A page is an invitation to the bundle, not a
replacement for it - the full slice is committed and linked."""

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


class BundleError(RuntimeError):
    """The bundle is not renderable, and the message says which part is missing."""


def _clean(text: str) -> str:
    """Strip ANSI escapes and per-line trailing whitespace. See the module docstring."""
    return "\n".join(ANSI.sub("", line).rstrip() for line in text.split("\n"))


def _offset(origin: datetime, moment: datetime) -> str:
    """A time as the reader thinks of it: how long after the fault went in."""
    seconds = int((moment - origin).total_seconds())
    sign = "-" if seconds < 0 else "+"
    seconds = abs(seconds)
    return f"T{sign}{seconds // 60}m{seconds % 60:02d}s"


def _parse(moment: str) -> datetime:
    return datetime.fromisoformat(moment)


def _at(origin: datetime, moment: str | None) -> str:
    """An offset, or an em dash. The bundles where nothing fired carry `null` for the alert
    time and for `seconds_to_alert`, and a page that rendered those as `T+0m00s` would be
    claiming an instant page for a fault that never paged at all."""
    return _offset(origin, _parse(moment)) if moment else "—"


def _duration(seconds: int | None) -> str:
    return f"{seconds // 60}m{seconds % 60:02d}s" if seconds is not None else "— never paged"


def _title(bundle_dir: Path, manifest: dict[str, Any]) -> str:
    """The narrative's own heading, which was written for a reader; the manifest's `title`
    only if the narrative has none."""
    incident = bundle_dir / "incident.md"
    if incident.is_file():
        for line in incident.read_text().split("\n"):
            if line.startswith("# "):
                return line[2:].strip()
    return str(manifest.get("title", manifest["scenario_id"]))


def _narrative_body(bundle_dir: Path) -> str:
    """`incident.md` without its front matter and without its own H1, which the page has
    already used as the title."""
    incident = bundle_dir / "incident.md"
    if not incident.is_file():
        return ""
    body = FRONT_MATTER.sub("", incident.read_text()).strip()
    lines = body.split("\n")
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    # Demote every heading one level so the narrative nests under the page's own sections.
    return "\n".join("#" + line if line.startswith("#") else line for line in lines).strip()


def _queries(bundle_dir: Path) -> dict[str, str]:
    """`queries.md` as {capture name: query}, so each capture can be shown with the question
    that produced it."""
    path = bundle_dir / "queries.md"
    if not path.is_file():
        return {}
    found: dict[str, str] = {}
    name: str | None = None
    inside = False
    body: list[str] = []
    for line in path.read_text().split("\n"):
        if line.startswith("## "):
            name, inside, body = line[3:].strip(), False, []
        elif line.startswith("```") and name:
            if inside:
                found[name] = "\n".join(body).strip()
                inside = False
            else:
                inside = True
        elif inside:
            body.append(line)
    return found


def _timeline(manifest: dict[str, Any]) -> list[str]:
    """The alert timeline, ordered as it happened and labelled by what it meant."""
    injected = _parse(manifest["t_inject"])
    paged = set(manifest.get("alerts_at_fire") or [])
    rows = sorted(
        manifest.get("alerts_over_window") or [],
        key=lambda a: (a["first_seen"], a["service"], a["alert"]),
    )
    if not rows:
        return ["_No alert fired over the capture window._"]

    lines = [
        "| when | service | alert | firing for | |",
        "|---|---|---|---:|---|",
    ]
    for alert in rows:
        key = f"{alert['alert']}/{alert['service']}"
        if alert.get("began_after_revert"):
            note = "began after the revert"
        elif key in paged:
            note = "**paged**"
        else:
            note = "joined later"
        lines.append(
            f"| {_offset(injected, _parse(alert['first_seen']))} "
            f"| `{alert['service']}` | {alert['alert']} "
            f"| {alert['minutes_firing']:.1f} min | {note} |"
        )
    return lines


def _captures(bundle_dir: Path, queries: dict[str, str]) -> list[str]:
    lines: list[str] = []
    metrics = sorted((bundle_dir / "metrics").glob("*.json"))
    if metrics:
        lines.append("| capture | query |")
        lines.append("|---|---|")
        for path in metrics:
            name = path.stem
            query = queries.get(name, "")
            rendered = f"`{query}`" if query else "_recorded without a stored query_"
            lines.append(f"| `metrics/{path.name}` | {rendered} |")
    logs = sorted((bundle_dir / "logs").glob("*.txt"))
    for path in logs:
        count = len(path.read_text().split("\n"))
        lines.append("")
        lines.append(f"`logs/{path.name}` — {count} lines.")
    return lines


def _log_excerpt(bundle_dir: Path) -> list[str]:
    logs = sorted((bundle_dir / "logs").glob("*.txt"))
    if not logs:
        return []
    path = logs[0]
    body = [line for line in _clean(path.read_text()).split("\n") if line.strip()]
    header = [line for line in body if line.startswith("#")]
    content = [line for line in body if not line.startswith("#")]
    if not content:
        return []
    excerpt = content[:LOG_EXCERPT_LINES]
    lines = ["## A look at the logs", ""]
    if header:
        lines.append(f"From `logs/{path.name}` ({header[-1].lstrip('# ').strip()}):")
        lines.append("")
    lines.append("```")
    lines.extend(excerpt)
    lines.append("```")
    lines.append("")
    remaining = len(content) - len(excerpt)
    if remaining > 0:
        lines.append(f"_{remaining} further lines are in the bundle._")
    return lines


def render(bundle_dir: Path) -> str:
    """One bundle as one Markdown page."""
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file():
        raise BundleError(f"{bundle_dir} has no manifest.json and is not a bundle")
    manifest = json.loads(manifest_path.read_text())
    scenario_id = manifest["scenario_id"]
    injected = _parse(manifest["t_inject"])
    invalid = bundle_dir / "INVALID.md"

    out: list[str] = [f"# {_title(bundle_dir, manifest)}", ""]

    if invalid.is_file():
        out += [
            "> ## ⚠ This bundle is not evidence of anything",
            ">",
            "> The fault was injected and **nothing happened** — no alert fired and no metric",
            "> moved. It is rendered here for completeness and because a catalogue that quietly",
            "> omits its failures is not a catalogue. The bundle's own",
            f"> [`INVALID.md`](../../evals/scenarios/artifacts/{manifest['split']}/"
            f"{scenario_id}/INVALID.md) explains why the fault could not fire.",
            "",
        ]

    injection = manifest.get("injection") or {}
    out += [
        "## The scenario",
        "",
        "| | |",
        "|---|---|",
        f"| scenario | `{scenario_id}` |",
        f"| fault class | **`{manifest['fault_class']}`** |",
        f"| expected remediation | `{manifest.get('expected_remediation_class', '—')}` |",
        f"| split | `{manifest['split']}` |",
        f"| injected at | `{injection.get('target', '—')}` via `{injection.get('method', '—')}` |",
        f"| time to page | {_duration(manifest.get('seconds_to_alert'))} |",
        f"| steady state captured | {manifest.get('seconds_of_steady_state', 0)}s |",
        f"| capture window | {manifest['window']['start']} → {manifest['window']['end']} |",
        "",
        "The clock below runs from the moment the fault went in.",
        "",
        "| | |",
        "|---|---|",
        f"| `t_inject` | {_offset(injected, injected)} |",
        f"| first alert firing | {_at(injected, manifest.get('t_alert_firing'))} |",
        f"| `t_revert` | {_at(injected, manifest.get('t_revert'))} |",
        f"| all clear | {_at(injected, manifest.get('t_clear'))} |",
        "",
        "## What fired, and when",
        "",
    ]
    out += _timeline(manifest)
    out += [
        "",
        "## What the bundle contains",
        "",
    ]
    out += _captures(bundle_dir, _queries(bundle_dir))

    excerpt = _log_excerpt(bundle_dir)
    if excerpt:
        out += ["", *excerpt]

    narrative = _narrative_body(bundle_dir)
    if narrative:
        out += [
            "",
            "## The incident record",
            "",
            "Written from the responder's chair, by someone who did not know the fault class",
            "or that anything had been injected. This text is also corpus material, which is",
            "why it never names the injector.",
            "",
            "**It keeps its own clock.** The table above is measured from the injection, which",
            "is the only origin the manifest records; a narrative's `T+` offsets are the",
            "responder's own and start wherever that responder started counting — usually the",
            "page, sometimes the injection, sometimes an event in the logs. The same moment can",
            "therefore carry two different offsets on this page. The absolute timestamps in the",
            "bundle are the tiebreak.",
            "",
            narrative,
        ]

    out += [
        "",
        "---",
        "",
        f"Rendered from [`evals/scenarios/artifacts/{manifest['split']}/{scenario_id}/`]"
        f"(../../evals/scenarios/artifacts/{manifest['split']}/{scenario_id}/) "
        f"by `faultline-render`. [All bundles](README.md).",
    ]
    return _clean("\n".join(out)).strip() + "\n"


def bundles(root: Path) -> list[Path]:
    """Every bundle under an artifacts root, in a fixed order."""
    return sorted(
        (path.parent for path in root.glob("*/*/manifest.json")),
        key=lambda p: (p.parent.name, p.name),
    )


def render_index(found: list[tuple[Path, dict[str, Any], str]]) -> str:
    """The index page: what exists, which split each came from, and one line about why
    rendering a holdout narrative for a person is not a contamination event."""
    dev = [row for row in found if row[1]["split"] == "dev"]
    holdout = [row for row in found if row[1]["split"] == "holdout"]
    valid = [row for row in found if not (row[0] / "INVALID.md").is_file()]

    out = [
        "# The bundles, rendered",
        "",
        f"Every recorded rehearsal in this repository as a readable page — {len(found)} in all: "
        f"**{len(valid)} runnable** ({len(_valid(dev))} dev, {len(_valid(holdout))} holdout) "
        f"and **{len(found) - len(valid)} that could not fire** "
        f"({len(dev) - len(_valid(dev))} dev).",
        "",
        "A bundle is what one rehearsal left behind — the manifest, the Prometheus captures,",
        "a slice of one service's logs, the exact queries, and the narrative a responder wrote",
        "afterwards without being told what had been done to the world. These pages are",
        "generated from those files by `faultline-render` and are byte-reproducible: the same",
        "bundle renders to the same page.",
        "",
        "**On the holdout pages.** They are here to be read by people, and that is not a",
        "contamination event. [ADR-0008](../adr/0008-contamination-model.md)'s quarantine",
        "is about two things: the holdout scenarios never enter a retrieval corpus, and no",
        "agent is run against them outside a pre-registered holdout entry. Neither is affected",
        "by a human reading a narrative that has been committed to this repository since it was",
        "recorded. What would break the quarantine is seeding these into the store or pointing",
        "the agent at them — and both are refused structurally, not by convention.",
        "",
        "## Dev split",
        "",
        "Where prompts and retrieval were fitted. Results on these scenarios are **not a",
        "benchmark** — see [RESULTS.md](../RESULTS.md).",
        "",
    ]
    out += _index_table(dev)
    out += [
        "",
        "## Holdout split",
        "",
        "Never fitted against, never in any retrieval corpus, and run only under a",
        "pre-registered entry.",
        "",
    ]
    out += _index_table(holdout)
    out += [
        "",
        "---",
        "",
        "Regenerate with `faultline-render --all`. No model calls and no live services.",
    ]
    return _clean("\n".join(out)).strip() + "\n"


def _valid(rows: list[tuple[Path, dict[str, Any], str]]) -> list[tuple[Path, dict[str, Any], str]]:
    return [row for row in rows if not (row[0] / "INVALID.md").is_file()]


def _index_table(rows: list[tuple[Path, dict[str, Any], str]]) -> list[str]:
    lines = ["| scenario | fault class | what happened |", "|---|---|---|"]
    for bundle_dir, manifest, page in sorted(rows, key=lambda r: r[1]["scenario_id"]):
        title = _title(bundle_dir, manifest)
        if (bundle_dir / "INVALID.md").is_file():
            summary = "**⚠ nothing fired** — the fault could not bind"
        else:
            count = len(manifest.get("alerts_over_window") or [])
            summary = f"{title} — {count} alerts over the window"
        lines.append(
            f"| [`{manifest['scenario_id']}`]({page}) | `{manifest['fault_class']}` | {summary} |"
        )
    return lines


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="faultline-render",
        description=(
            "Render recorded rehearsal bundles as Markdown pages for a human reader "
            "(T5.3b). Deterministic: the same bundle renders to the same bytes."
        ),
        epilog=(
            "Reads committed files only - no model calls, no live services, and nothing is "
            "written inside the bundle trees. Holdout bundles render like any other: the "
            "quarantine in ADR-0008 governs the corpus and the agent, not people."
        ),
    )
    p.add_argument("scenario_ids", nargs="*", help="default: every bundle, with --all")
    p.add_argument("--all", action="store_true", help="render every bundle and the index")
    p.add_argument("--artifacts-root", default=str(DEFAULT_ARTIFACTS_ROOT))
    p.add_argument("--out", default=str(DEFAULT_OUT), help="default: %(default)s")
    p.add_argument("--check", action="store_true", help="render and report drift, write nothing")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root, out_dir = Path(args.artifacts_root), Path(args.out)
    if not args.all and not args.scenario_ids:
        print("nothing to do: name a scenario or pass --all")
        return 2

    wanted = set(args.scenario_ids)
    found = [path for path in bundles(root) if not wanted or path.name in wanted]
    missing = wanted - {path.name for path in found}
    if missing:
        print(f"no such bundle: {', '.join(sorted(missing))}")
        return 2

    if not args.check:
        out_dir.mkdir(parents=True, exist_ok=True)

    drifted: list[str] = []
    rendered: list[tuple[Path, dict[str, Any], str]] = []
    for bundle_dir in found:
        manifest = json.loads((bundle_dir / "manifest.json").read_text())
        page = f"{manifest['scenario_id']}.md"
        body = render(bundle_dir)
        rendered.append((bundle_dir, manifest, page))
        target = out_dir / page
        if args.check:
            if not target.is_file() or target.read_text() != body:
                drifted.append(page)
        else:
            target.write_text(body)
            print(f"  {target}")

    if wanted:
        return 0

    index = render_index(rendered)
    target = out_dir / "README.md"
    if args.check:
        if not target.is_file() or target.read_text() != index:
            drifted.append("README.md")
        if drifted:
            print(f"stale: {', '.join(drifted)} - run `faultline-render --all`")
            return 1
        print(f"{len(rendered)} pages up to date")
    else:
        target.write_text(index)
        print(f"  {target}")
        print(f"{len(rendered)} bundles rendered")
    return 0


def run_cli() -> None:  # pragma: no cover - console entry point
    sys.exit(main())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
