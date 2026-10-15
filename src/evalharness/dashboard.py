"""The eval dashboard (T7.4): accuracy, grounding, cost and latency by version and by class.

The execution plan's T7.4 row: *"A small dashboard over the eval DB: accuracy, grounding, cost, and
latency across prompt/model versions and scenario classes. Charts straight off the eval schema;
version timeline annotated with what changed."*

**Off the eval schema, read the way the eval DB is filled.** `faultline-eval-db load` flattens each
run manifest into an `eval_runs` row with `evaldb.row_of`; this module reads the same rows with
the same function (`evaldb.read_runs`), so the dashboard and the database cannot disagree about a
run, and it needs no running Postgres to regenerate. Its output is one self-contained HTML file,
`evals/dashboard/index.html`: no script, no external asset, charts as inline SVG. It is committed
and `tests/test_dashboard.py` regenerates it from `evals/runs/` and compares, the rule README's
generated blocks are held to - a dashboard that drifts from the record is a screenshot.

**A version** is a runtime stamp (`prompts:...` for Faultline, `baseline:...` for B0-B2) on one
world generation: the two things the repository treats as breaking comparability. **No rate
without its n and an interval**: every accuracy carries a Wilson 95 % interval, and the by-class
table gives counts, not rates, as every report here does at that size.

**What changed** comes from `evals/dashboard/versions.tsv`: one written line per stamp, naming
the change that moved it and the document that records it. A first draft linked the first line of
`docs/PLAN.md` naming each digest, and was worse on both counts - the first mention of a digest is
often a later sweep citing it rather than the move, and every PLAN edit shifted the line links. A
version the file does not annotate fails `tests/test_dashboard.py`, so a new stamp cannot reach
the chart without its reason. A T7.3 switch, which moves no stamp, is annotated as such.
"""

from __future__ import annotations

import argparse
import html
import math
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evalharness.evaldb import Row, read_runs

REPO = Path(__file__).resolve().parents[2]
DEFAULT_RUNS = REPO / "evals" / "runs"
DEFAULT_NOTES = REPO / "evals" / "dashboard" / "versions.tsv"
DEFAULT_OUT = REPO / "evals" / "dashboard" / "index.html"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def variant_of(row: Row) -> str:
    """What a run changed from its stamp's standing pipeline: specialists withheld
    (`ablation`) or T7.3's switches (`ablation_config`). Empty for the standing pipeline.

    A switch moves no stamp by design (`PREREGISTRATION-T7.3.md`), so without this an ablation
    arm's runs would be pooled with the standing pipeline's under one version."""
    manifest = row.manifest
    parts = []
    withheld = manifest.get("ablation") or []
    if withheld:
        parts.append("without " + ", ".join(sorted(str(w) for w in withheld)))
    for key, value in sorted((manifest.get("ablation_config") or {}).items()):
        shown = value if isinstance(value, (str, int, float, bool)) else "custom"
        if key == "role_models" and isinstance(value, dict):
            shown = ",".join(sorted({str(m) for m in value.values()}))
        text = f"{key}={shown}"
        parts.append(text if len(text) <= 48 else text[:45] + "...")
    return "; ".join(parts)


@dataclass
class Version:
    runtime: str
    generation: str
    variant: str = ""
    rows: list[Row] = field(default_factory=list)

    @property
    def first(self) -> str:
        return min(str(r.values.get("started_at") or "") for r in self.rows)

    @property
    def digest(self) -> str:
        """The key into `versions.tsv`: the digest, or B0's version."""
        tail = self.runtime.split("+", 1)[-1]
        return tail.rsplit(":", 1)[-1] if ":" in tail else tail

    @property
    def label(self) -> str:
        stamp = self.runtime.split("+", 1)[-1]
        return f"{stamp} [{self.variant}]" if self.variant else stamp


def _answered(rows: list[Row], key: str) -> tuple[int, int]:
    counted = [r for r in rows if not r.values.get(f"{key}_abstained")]
    return sum(bool(r.values.get(f"{key}_correct")) for r in counted), len(counted)


def _service(rows: list[Row]) -> tuple[int, int]:
    labels = [((r.manifest.get("score") or {}).get("service") or {}) for r in rows]
    counted = [label for label in labels if label and not label.get("abstained")]
    return sum(bool(label.get("correct")) for label in counted), len(counted)


def _metric(row: Row, *path: str) -> Any:
    value: Any = row.manifest.get("metrics") or {}
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def versions_of(rows: list[Row]) -> list[Version]:
    grouped: dict[tuple[str, str, str], Version] = {}
    for row in rows:
        runtime = row.values.get("runtime_version")
        if row.outcome != "scored" or not runtime:
            continue
        generation = str(row.values.get("world_generation") or "unrecorded")
        variant = variant_of(row)
        key = (str(runtime), generation, variant)
        grouped.setdefault(key, Version(str(runtime), generation, variant)).rows.append(row)
    return sorted(grouped.values(), key=lambda v: (v.first, v.runtime, v.generation, v.variant))


@dataclass(frozen=True)
class Note:
    what: str
    source: str


def read_notes(path: Path) -> dict[str, Note]:
    """`versions.tsv`: `#` lines are comments, the first other line is the header."""
    notes: dict[str, Note] = {}
    lines = [line for line in path.read_text().splitlines() if line and not line.startswith("#")]
    for line in lines[1:]:
        version, what, source = line.split("\t")
        notes[version] = Note(what, source)
    return notes


def note_for(version: Version, notes: dict[str, Note]) -> Note | None:
    """A variant's own row if it has one; otherwise a T7.3 switch is said to be one, and a stamp
    takes its digest's row."""
    if version.label in notes:
        return notes[version.label]
    if version.variant and not version.variant.startswith("without "):
        return Note(
            f"A T7.3 ablation switch ({version.variant}) on this stamp, which a switch does not "
            "move.",
            "docs/ABLATIONS.md",
        )
    if version.variant:
        return None
    return notes.get(version.digest)


def pct(x: float) -> str:
    return "n/a" if x != x else f"{100 * x:.0f}%"


def rate(k: int, n: int) -> str:
    if n == 0:
        return "-"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {pct(k / n)} <small>({pct(lo)}-{pct(hi)})</small>"


def median(values: list[float]) -> str:
    return f"{statistics.median(values):.2f}" if values else "-"


# --- the chart ---------------------------------------------------------------------------------


def accuracy_chart(versions: list[Version]) -> str:
    """Fault-class accuracy per version in first-seen order, each a point with its Wilson
    interval; Faultline's stamps and the baselines drawn apart."""
    width, height, left, top, bottom = 900, 260, 46, 16, 40
    plot_w, plot_h = width - left - 16, height - top - bottom
    step = plot_w / max(1, len(versions))
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        'aria-label="Fault-class accuracy by version, with 95% Wilson intervals">'
    ]
    for tick in (0, 0.25, 0.5, 0.75, 1.0):
        y = top + plot_h * (1 - tick)
        parts.append(
            f'<line x1="{left}" x2="{width - 16}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>'
        )
        parts.append(f'<text x="{left - 6}" y="{y + 4:.1f}" class="tick" text-anchor="end">')
        parts.append(f"{int(tick * 100)}%</text>")
    for index, version in enumerate(versions):
        k, n = _answered(version.rows, "fault_class")
        if n == 0:
            continue
        x = left + step * (index + 0.5)
        lo, hi = wilson(k, n)
        kind = "baseline" if "baseline:" in version.runtime else "faultline"
        if version.variant:
            kind += " variant"
        y = top + plot_h * (1 - k / n)
        parts.append(
            f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top + plot_h * (1 - hi):.1f}" '
            f'y2="{top + plot_h * (1 - lo):.1f}" class="ci {kind}"/>'
        )
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" class="{kind}">'
            f"<title>{html.escape(version.label)} on {html.escape(version.generation)}: "
            f"{k}/{n}</title></circle>"
        )
        parts.append(
            f'<text x="{x:.1f}" y="{height - bottom + 14}" class="tick" text-anchor="middle">'
            f"{index + 1}</text>"
        )
    parts.append("</svg>")
    return "".join(parts)


# --- the page ----------------------------------------------------------------------------------

STYLE = """
:root { color-scheme: light dark; --fg: #1f2328; --muted: #59636e; --bg: #ffffff; --line: #d1d9e0;
  --faultline: #2563eb; --baseline: #b45309; }
@media (prefers-color-scheme: dark) { :root { --fg: #e6edf3; --muted: #9198a1; --bg: #0d1117;
  --line: #30363d; --faultline: #60a5fa; --baseline: #f59e0b; } }
body { font: 14px/1.5 system-ui, sans-serif; color: var(--fg); background: var(--bg);
  max-width: 1100px; margin: 24px auto; padding: 0 16px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0 24px; font-size: 13px; }
th, td { border-bottom: 1px solid var(--line); padding: 4px 6px; text-align: left;
  vertical-align: top; }
th { font-weight: 600; } small, .muted { color: var(--muted); }
.wide { overflow-x: auto; } svg { width: 100%; height: auto; } .grid { stroke: var(--line); }
.tick { fill: var(--muted); font-size: 11px; }
circle.faultline { fill: var(--faultline); } circle.baseline { fill: var(--baseline); }
circle.variant { fill: var(--bg); stroke: var(--faultline); stroke-width: 2; }
line.ci.faultline { stroke: var(--faultline); stroke-width: 2; }
line.ci.baseline { stroke: var(--baseline); stroke-width: 2; }
.key-f { color: var(--faultline); } .key-b { color: var(--baseline); }
"""


def render(rows: list[Row], notes: dict[str, Note], root: str = "../../") -> str:
    versions = versions_of(rows)
    unstamped = sum(
        1 for r in rows if r.outcome == "scored" and not r.values.get("runtime_version")
    )
    out = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Faultline eval dashboard</title>",
        f"<style>{STYLE}</style></head><body>",
        "<h1>Faultline eval dashboard</h1>",
        "<p class='muted'>T7.4. Generated by <code>faultline-dashboard</code> from "
        f"<code>evals/runs/</code> ({len(rows)} run manifests, read as <code>eval_runs</code> "
        "rows by <code>evaldb.read_runs</code>); <code>tests/test_dashboard.py</code> fails when "
        "this page and the record disagree. Scored runs only, every sweep and both splits pooled "
        "per version - an instrument for seeing what moved, not a published figure; those are in "
        "the dated reports under <code>evals/runs/</code>. Every rate is k/n with a Wilson 95% "
        f"interval. {unstamped} scored runs predate the runtime stamp and are not charted.</p>",
        "<h2>Fault-class accuracy by version</h2>",
        "<p class='muted'>One point per version, in the order each first ran; "
        "<span class='key-f'>Faultline stamps</span> and "
        "<span class='key-b'>baselines</span>; a hollow point is a variant of a stamp (specialists "
        "withheld, or a T7.3 switch on), which moves no stamp. Numbers are the table's.</p>",
        accuracy_chart(versions),
        "<h2>Versions</h2>",
        "<div class='wide'><table><thead><tr><th>#</th><th>version</th><th>world</th>"
        "<th>first run</th>"
        "<th>scored</th><th>fault class</th><th>culprit service</th><th>fix class</th>"
        "<th>citation violations / regenerated</th><th>tool-call validity (median)</th>"
        "<th>median $</th><th>median s to report</th><th>what changed</th>"
        "</tr></thead><tbody>",
    ]
    for index, version in enumerate(versions, start=1):
        rows_v = version.rows
        violations = sum(int(_metric(r, "citations", "violations") or 0) for r in rows_v)
        regenerated = sum(bool(_metric(r, "citations", "regenerated")) for r in rows_v)
        validity = [
            float(v) for r in rows_v if (v := _metric(r, "tool_calls", "validity_rate")) is not None
        ]
        costs = [float(c) for r in rows_v if (c := r.values.get("cost_usd")) is not None]
        latency = [
            float(ms) / 1000 for r in rows_v if (ms := r.values.get("latency_ms")) is not None
        ]
        note = note_for(version, notes)
        changed = (
            f'{html.escape(note.what)} <a href="{root}{html.escape(note.source)}">'
            f"{html.escape(note.source)}</a>"
            if note
            else "<span class='muted'>not annotated</span>"
        )
        out.append(
            f"<tr><td>{index}</td><td><code>{html.escape(version.label)}</code></td>"
            f"<td><code>{html.escape(version.generation)}</code></td>"
            f"<td>{html.escape(version.first[:10])}</td><td>{len(rows_v)}</td>"
            f"<td>{rate(*_answered(rows_v, 'fault_class'))}</td>"
            f"<td>{rate(*_service(rows_v))}</td><td>{rate(*_answered(rows_v, 'fix_class'))}</td>"
            f"<td>{violations} / {regenerated}</td>"
            f"<td>{median(validity) if validity else '-'}</td>"
            f"<td>{median(costs)}</td><td>{median(latency) if latency else '-'}</td>"
            f"<td>{changed}</td></tr>"
        )
    out.append("</tbody></table></div>")
    out += by_class(versions)
    out.append("</body></html>")
    return "\n".join(out) + "\n"


def by_class(versions: list[Version]) -> list[str]:
    """Counts by fault class on the most recent world generation, for every version that ran on
    it - counts and never rates, because no class here has five scenarios in one version."""
    if not versions:
        return []
    latest = max(versions, key=lambda v: v.first).generation
    on_latest = [v for v in versions if v.generation == latest]
    classes: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
    for version in on_latest:
        per: dict[str, list[Row]] = defaultdict(list)
        for row in version.rows:
            per[str(row.values.get("fault_class_truth") or "unlabelled")].append(row)
        for cls, members in per.items():
            classes[cls][version.label] = _answered(members, "fault_class")
    number = {id(v): index for index, v in enumerate(versions, start=1)}
    labels = [v.label for v in on_latest]
    out = [
        f"<h2>By fault class, world <code>{html.escape(latest)}</code></h2>",
        "<p class='muted'>Right / answered, per version that ran on the newest world, columns "
        "numbered as the versions table. Counts, not rates: no class has five scenarios in one "
        "version.</p>",
        "<div class='wide'><table><thead><tr><th>class</th>"
        + "".join(f'<th title="{html.escape(v.label)}">#{number[id(v)]}</th>' for v in on_latest)
        + "</tr></thead><tbody>",
    ]
    for cls in sorted(classes):
        cells = []
        for label in labels:
            k, n = classes[cls].get(label, (0, 0))
            cells.append(f"<td>{k}/{n}</td>" if n else "<td>-</td>")
        out.append(f"<tr><td>{html.escape(cls)}</td>{''.join(cells)}</tr>")
    out.append("</tbody></table></div>")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="faultline-dashboard",
        description="Write the eval dashboard (T7.4) from the run record: one self-contained HTML "
        "page of accuracy, grounding, cost and latency by version and by fault class.",
    )
    parser.add_argument("runs", nargs="?", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--notes", type=Path, default=DEFAULT_NOTES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--stdout", action="store_true", help="print instead of writing --out")
    args = parser.parse_args(argv)
    page = render(read_runs(args.runs), read_notes(args.notes))
    if args.stdout:
        sys.stdout.write(page)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(page)
        print(f"wrote {args.out}")
    return 0


def run_cli() -> None:  # pragma: no cover - console entry point
    sys.exit(main())
