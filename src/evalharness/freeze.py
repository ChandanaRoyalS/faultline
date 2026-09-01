"""The holdout freeze manifest: the things ADR-0022 §3.3 says must not move (T4.6, T7.54).

**"Frozen" has to mean something a script can check, or it means nothing.** ADR-0022 enumerated
six hashes and this computes them - **and T7.54 added a seventh, `world`, because the original six
froze everything the harness *constructs* and nothing it *observes*.** Every one of the six is
defined inside this repository in Python or in the database; the world the experiment runs in was
treated as scenery. It is not scenery, it is the largest uncontrolled input, and a freeze that
misses it lets two runs pass every check while having executed against different worlds. That is
not hypothetical: T7.54 found 69 of 97 recorded runs attributed to the wrong world generation.

It is a harness module, not a product one, and it reads the
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


def world_state(reference_container: str = "cart-service") -> dict[str, Any]:
    """The world the experiment runs **in**, and the capability surface it runs **with** (T7.54).

    Two guards, kept separate on purpose. `capability.py` says so itself: `CAPABILITY_VERSION`
    *"deliberately does not cover the world … this one would double-fire on it and teach people to
    ignore both."* The same argument says the world does not cover capability, so both are here and
    neither is folded into the other.

    **What is included and why each has the same claim as the original six:**

    - `compose_digest` - the three layered compose files. The world's definition.
    - `observability_digest` - the seven alerting, scrape and collector files. **Arguably the most
      load-bearing item in this manifest**: it decides what the agent's tools can see at all, which
      is nearer to the experiment than the compose layer is.
    - `ffs_stub_source_digest` - the injected stub's source: the one world component built here.
    - `otel_demo_image_digest` - the immutable half of a mutable tag (ADR-0026). Requires a live
      container; `None` when there is none, and `None` is recorded as **unverifiable**, never as
      unchanged.
    - `capability_version` - `CAPABILITY_VERSION`: the tool surface, `CAPTURE_SET` and
      `TOOL_BEHAVIOUR_REVISION`.
      `tool_layer.git_sha` does *not* cover this: a sha moves for unrelated commits and says nothing
      about whether what an agent could ask changed.

    **`ffs_stub_image_id` is deliberately excluded.** ADR-0014 records it and refuses to compare it:
    a rebuild churns the id from unchanged source, so it would fire on nothing. Freezing a field
    that moves on its own trains a reader to ignore the manifest.
    """
    from evalharness.capability import capability_version
    from evalharness.provenance import (
        compose_digest,
        ffs_stub_source_digest,
        image_content_digest,
        observability_digest,
    )

    state: dict[str, Any] = {
        "compose_digest": compose_digest(),
        "observability_digest": observability_digest(),
        "ffs_stub_source_digest": ffs_stub_source_digest(),
        "otel_demo_image_digest": image_content_digest(reference_container),
        "capability_version": capability_version(),
    }
    state["unverifiable_fields"] = sorted(k for k, v in state.items() if v is None)
    return state


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
    """All seven, plus the pipeline stamp they exist to protect."""
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
        "world": world_state(),
    }


FROZEN_KEYS = ("runtime_version", "prompts", "corpus", "model_map", "budget", "judge", "world")
"""Compared whole. `tool_layer` is handled separately below - its dirty flag moves during a run."""


def diff(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """What moved between two manifests. Empty means the freeze held.

    **Absence is reported as `unverifiable`, never as unchanged (T7.54).** Every freeze manifest
    written before T7.54 lacks `world`, and comparing two of them tells a reader nothing about
    whether the world moved between them - which is exactly how 69 runs came to be attributed to a
    world they did not execute against. A check that answers "no difference" to a question it
    cannot see is worse than one that answers "I cannot see it".
    """
    moved: list[str] = []
    for key in FROZEN_KEYS:
        if key not in before or key not in after:
            moved.append(f"{key}:unverifiable")
        elif before[key] != after[key]:
            moved.append(key)
    if before.get("world", {}).get("unverifiable_fields") or after.get("world", {}).get(
        "unverifiable_fields"
    ):
        moved.append("world:unverifiable")
    # The tool layer's dirty flag moves as files are written during a run; the sha is what binds.
    if before.get("tool_layer", {}).get("git_sha") != after.get("tool_layer", {}).get("git_sha"):
        moved.append("tool_layer.git_sha")
    return moved


def write(path: Path, manifest: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path
