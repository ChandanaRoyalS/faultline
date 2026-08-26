"""The holdout freeze manifest: the six things ADR-0022 §3.3 says must not move (T4.6).

**"Frozen" has to mean something a script can check, or it means nothing.** ADR-0022 enumerated
six hashes and this computes them. It is a harness module, not a product one, and it reads the
product from the outside - which is the only way a freeze check can be trusted: a freeze that
asks the thing being frozen whether it has changed is not a check.

The manifest is written before any holdout scenario runs, committed on its own, and re-verified
after the run. A holdout run whose manifest does not match the dev run it is compared against is
not a comparison (ADR-0022 §3.3), and this is what makes that statement enforceable.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

AGENT_ROLES = ("planner", "metrics", "logs", "changes", "traces", "synthesizer", "scribe")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def prompts_hash() -> dict[str, Any]:
    """Every prompt string in `faultline.agents`, concatenated in sorted order."""
    from faultline.agents import roles

    names = sorted(
        n for n in dir(roles) if n.endswith("_SYSTEM") and isinstance(getattr(roles, n), str)
    )
    joined = "\n\x00\n".join(getattr(roles, n) for n in names)
    return {"constants": names, "sha256": _sha(joined), "chars": len(joined)}


def corpus_state(dsn: str) -> dict[str, Any]:
    """Row count, a content hash, and **the assertion that no holdout chunk exists**.

    ADR-0008 axis 1: holdout artifacts never enter any retrieval corpus. This is the one freeze
    item that is also a contamination check, so it reports `holdout_chunks` explicitly rather
    than folding it into the hash - a number that must be zero deserves to be read as a number.
    """
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM incident_chunks")
        rows = int((cur.fetchone() or [0])[0])
        cur.execute(
            "SELECT document_id, section FROM incident_chunks ORDER BY document_id, section"
        )
        digest = _sha("\n".join(f"{d}|{s}" for d, s in cur.fetchall()))
        cur.execute(
            "SELECT count(*) FROM incident_chunks WHERE document_id = ANY(%s)",
            (holdout_origins(),),
        )
        holdout = int((cur.fetchone() or [0])[0])
        cur.execute("SELECT DISTINCT document_id FROM incident_chunks ORDER BY 1")
        documents = [row[0] for row in cur.fetchall()]
    return {
        "rows": rows,
        "sha256": digest,
        "documents": documents,
        "holdout_chunks": holdout,
    }


def holdout_origins() -> list[str]:
    root = REPO_ROOT / "evals/scenarios/artifacts/holdout"
    return sorted(f"scenario:{p.name}" for p in root.iterdir() if p.is_dir())


def model_map() -> dict[str, Any]:
    from faultline.agents.settings import AgentSettings

    settings = AgentSettings()
    return {
        "models": settings.effective_models(list(AGENT_ROLES)),
        "effort_default": settings.effort,
        "role_efforts": dict(settings.role_efforts),
    }


def budget_bounds(max_tool_calls: int, max_tokens: int) -> dict[str, Any]:
    from faultline.agents.settings import AgentSettings

    settings = AgentSettings()
    return {
        "max_tool_calls_per_specialist": max_tool_calls,
        "max_tokens": max_tokens,
        "wall_clock_seconds": settings.budget_wall_clock_seconds,
        "max_dispatch_rounds": settings.budget_max_dispatch_rounds,
    }


def tool_layer() -> dict[str, Any]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
        )
        return result.stdout.strip()

    return {"git_sha": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain"))}


def judge_state() -> dict[str, Any]:
    """Model id and prompt hash, **separately from the agent's** (ADR-0020 §1)."""
    from evalharness.judge import JUDGE_SYSTEM, JudgeSettings

    settings = JudgeSettings.from_env()
    return {
        "model": settings.model or None,
        "prompt_sha256": _sha(JUDGE_SYSTEM),
        "allow_shared_lineage": settings.allow_shared_lineage,
    }


def build(dsn: str, *, max_tool_calls: int = 4, max_tokens: int = 120_000) -> dict[str, Any]:
    """All six, plus the pipeline stamp they exist to protect."""
    from faultline.agents.stamp import runtime_version

    return {
        "frozen_for": "T4.6 holdout",
        "runtime_version": runtime_version(),
        "prompts": prompts_hash(),
        "corpus": corpus_state(dsn),
        "model_map": model_map(),
        "budget": budget_bounds(max_tool_calls, max_tokens),
        "tool_layer": tool_layer(),
        "judge": judge_state(),
    }


def diff(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """What moved between two manifests. Empty means the freeze held."""
    moved: list[str] = []
    for key in ("runtime_version", "prompts", "corpus", "model_map", "budget", "judge"):
        if before.get(key) != after.get(key):
            moved.append(key)
    # The tool layer's dirty flag moves as files are written during a run; the sha is what binds.
    if before.get("tool_layer", {}).get("git_sha") != after.get("tool_layer", {}).get("git_sha"):
        moved.append("tool_layer.git_sha")
    return moved


def write(path: Path, manifest: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path
