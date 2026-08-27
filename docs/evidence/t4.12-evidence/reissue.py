"""T4.12's registered primary endpoint: does a run re-ask a stream that already fell silent?

The pre-registration made the endpoint behavioural rather than coverage. Coverage is one draw
from a spread T4.10 measured at 2.6x; the re-issue count reads the behaviour an instruction
about silence actually names.

A re-issue is a tool call to the same `(tool, service)` pair as an earlier call in the same
trajectory whose envelope carried `empty="true"`. Each call's window is reported alongside, so
a materially-changed re-ask can be told from a bare repeat.

    uv run python docs/evidence/t4.12-evidence/reissue.py 'evals/runs/2026*/manifest.json'

Read-only: no model call, no injection, no write.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import psycopg

from faultline.context.settings import ContextSettings

WINDOW = re.compile(r'window="([^"]*)"')


def window_of(envelope: str) -> str:
    """The window a tool result covers, or "" when the envelope does not name one."""
    found = WINDOW.search(envelope)
    return found.group(1) if found else ""


def is_empty(envelope: str) -> bool:
    """`empty` is a typed field on the envelope's first line, per ADR-0019."""
    return 'empty="true"' in envelope.split("\n")[0]


def analyse(pattern: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with psycopg.connect(ContextSettings().postgres_dsn) as conn, conn.cursor() as cur:
        for path in sorted(glob.glob(pattern)):
            manifest = json.loads(Path(path).read_text())
            score = manifest.get("score")
            if not score:
                continue  # a discarded run has no score
            cur.execute(
                "SELECT seq, tool, request, envelope FROM trajectory_tool_calls "
                "WHERE trajectory_id=%s ORDER BY seq",
                (score["trajectory_id"],),
            )
            calls = cur.fetchall()
            silent: dict[tuple[str, str], str] = {}
            reissues: list[dict[str, Any]] = []
            for seq, tool, request, envelope in calls:
                key = (tool, (request or {}).get("service", "?"))
                if key in silent:
                    reissues.append(
                        {
                            "seq": seq,
                            "tool": tool,
                            "service": key[1],
                            "same_window": window_of(envelope) == silent[key],
                        }
                    )
                if is_empty(envelope):
                    silent[key] = window_of(envelope)
            rows.append(
                {
                    "run": os.path.basename(os.path.dirname(path)),
                    "scenario": score["scenario_id"],
                    "stamp": score["runtime_version"].rsplit(":", 1)[-1],
                    "returned": score["fault_class"]["returned"],
                    "abstained": score["fault_class"]["abstained"],
                    "tools": sorted({tool for _, tool, _, _ in calls}),
                    "silent_streams": len(silent),
                    "reissues": reissues,
                }
            )
    return rows


def main() -> None:
    for row in analyse(sys.argv[1]):
        count = len(row["reissues"])
        flag = f"RE-ISSUE x{count}" if count else "clean"
        outcome = "ABST" if row["abstained"] else row["returned"]
        tools = ",".join(tool.split("_")[0] for tool in row["tools"])
        print(
            f"{row['scenario']:32} {row['stamp']} {outcome:22} "
            f"silent={row['silent_streams']} {flag}  tools={tools}"
        )
        for hit in row["reissues"]:
            print(
                f"      seq {hit['seq']}: {hit['tool']} @ {hit['service']} "
                f"(same window: {hit['same_window']})"
            )


if __name__ == "__main__":
    main()
