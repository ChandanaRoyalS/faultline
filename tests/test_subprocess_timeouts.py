"""Every subprocess the harness runs is bounded, or is on a list saying why it is not.

**Found 2026-09-17, after three sweep blocks produced zero scored runs between them.** The third
sat inside `faultline-eval`'s baseline gate for thirteen minutes with no output, no child process
and nothing written to disk - in `docker stats --no-stream` across thirty containers, through a
`subprocess.run` with no timeout. The two blocks before it had died the same way and were read as
a settling problem, because a hung process and a slow one look identical from outside.

The rule is not *bound everything*: `faultline-eval` and `faultline-investigate` are the work, and
a timeout on them would kill a run for thinking. The rule is that **an unbounded call is a
decision someone made on purpose**, and this test is where that decision is written down.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

UNBOUNDED_BY_DESIGN = {
    "orchestrator/runner.py": "runs the agent; the agent is what takes the time",
    "run.py": "launches faultline-investigate, which is the run itself",
    "sweep.py": (
        "launches faultline-eval, which is one scored run; its docker verbs are bounded "
        "and test_the_sweeps_recycle_is_bounded holds that line"
    ),
    "blind_cli.py": "wraps a full command on the operator's behalf",
    "depthpilot.py": "a pilot driver, run attended",
    "demo.py": "a demo, run attended",
    "baseline.py": "launches a baseline run",
    "provenance.py": "git, in-process and local",
    "freeze.py": "reads the world's digests at run start",
}
"""Each entry is a reason, not a permission. A new unbounded call has to be argued for here."""


def _calls_without_timeout(path: Path) -> list[int]:
    tree = ast.parse(path.read_text())
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            f"{func.value.id}.{func.attr}"
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
            else None
        )
        if name != "subprocess.run":
            continue
        if not any(kw.arg == "timeout" for kw in node.keywords):
            lines.append(node.lineno)
    return lines


def test_the_gates_docker_calls_are_bounded() -> None:
    """`rehearse` is what the baseline gate reads the world through, and it holds the call that
    hung: `docker stats --no-stream`. Every `subprocess.run` in it carries a timeout."""
    assert _calls_without_timeout(SRC / "evalharness" / "rehearse.py") == []


def test_the_injectors_docker_verbs_are_bounded() -> None:
    """The writing verbs. **A revert that never returns leaves a fault in the world** - which is
    how a killed sweep left `product-catalog-flag-failure` injected for sixteen hours, refusing
    every run made after it until a person noticed."""
    assert _calls_without_timeout(SRC / "injector" / "docker.py") == []


def test_the_sweeps_recycle_is_bounded() -> None:
    """The recycle restarts four containers between passes, unattended, in the one driver whose
    whole purpose is running without anyone watching."""
    unbounded = _calls_without_timeout(SRC / "evalharness" / "sweep.py")

    # The eval launcher is the exception, and it is the only one.
    source = (SRC / "evalharness" / "sweep.py").read_text().splitlines()
    for line in unbounded:
        assert "faultline-eval" in source[line - 1] or "argv" in source[line - 1], (
            f"sweep.py:{line} runs a subprocess with no timeout and is not the eval launcher"
        )


def test_every_other_unbounded_call_is_on_the_list_with_a_reason() -> None:
    """The guard that makes the two above stay true. A new `subprocess.run` with no timeout fails
    here until someone writes down why it should not have one - which is the argument, not the
    ceremony: the three defects this file exists for were each invisible until a sweep stopped."""
    for path in sorted(SRC.rglob("*.py")):
        if not _calls_without_timeout(path):
            continue
        key = str(path.relative_to(SRC)).split("/", 1)[-1]
        assert key in UNBOUNDED_BY_DESIGN or path.name in UNBOUNDED_BY_DESIGN, (
            f"{path.relative_to(SRC)} runs an unbounded subprocess and is not on "
            "UNBOUNDED_BY_DESIGN. Add a timeout, or add the file with the reason it cannot have one"
        )
