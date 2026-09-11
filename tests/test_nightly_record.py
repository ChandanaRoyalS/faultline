"""Where a night's runs land (T4.5): `scripts/nightly_record.sh`, run against a real git remote.

The nightly's Postgres dies with the job; the durable eval database is `evals/runs/` in git. The
script puts a night's run directories on a results branch, on top of main, never on main. These
tests build a bare remote and a clone in a temp directory and run the script for real - the
alternative, asserting on the script's text, is how the smoke workflow kept a loop that could not
have passed.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "nightly_record.sh"

OWNER = ("chandana", "chandanaroyal719@gmail.com")


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": OWNER[0],
        "GIT_AUTHOR_EMAIL": OWNER[1],
        "GIT_COMMITTER_NAME": OWNER[0],
        "GIT_COMMITTER_EMAIL": OWNER[1],
    }
    out = subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=check
    )
    return out.stdout.strip()


@pytest.fixture
def world(tmp_path: Path) -> tuple[Path, Path]:
    """A bare `origin` with `main` carrying one committed run directory, and a clone of it."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))

    seed = tmp_path / "seed"
    _git(tmp_path, "clone", "-q", str(origin), str(seed))
    _git(seed, "checkout", "-q", "-b", "main")
    (seed / "evals" / "runs" / "20260901T000000Z-old-run").mkdir(parents=True)
    (seed / "evals" / "runs" / "20260901T000000Z-old-run" / "manifest.json").write_text("{}\n")
    (seed / "evals" / "runs" / "INVALID.md").write_text("# tracked\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "seed (#1)")
    _git(seed, "push", "-q", "origin", "main")

    clone = tmp_path / "runner"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    return origin, clone


def _night(clone: Path, stamp: str, scenario: str = "cart-bad-image-tag") -> str:
    run_dir = clone / "evals" / "runs" / f"{stamp}-{scenario}"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text('{"tier": "nightly"}\n')
    (run_dir / "score.json").write_text("{}\n")
    return f"evals/runs/{stamp}-{scenario}"


def _record(clone: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=clone,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def test_a_night_lands_on_the_results_branch_and_never_on_main(world: tuple[Path, Path]) -> None:
    origin, clone = world
    new = _night(clone, "20260912T040000Z")

    result = _record(clone, "nightly-results", "eval-nightly run 1")

    assert result.returncode == 0, result.stderr + result.stdout
    assert "recorded 1 run directory" in result.stdout
    # On the remote's results branch, on top of main.
    files = _git(origin, "ls-tree", "-r", "--name-only", "nightly-results")
    assert f"{new}/manifest.json" in files
    assert "evals/runs/20260901T000000Z-old-run/manifest.json" in files
    assert _git(origin, "merge-base", "--is-ancestor", "main", "nightly-results") == ""
    # And not on main.
    assert _git(origin, "rev-parse", "main") == _git(origin, "rev-parse", "main^{commit}")
    assert new not in _git(origin, "ls-tree", "-r", "--name-only", "main")


def test_the_commit_is_the_owners_and_says_which_run_made_it(world: tuple[Path, Path]) -> None:
    """Every commit in this repository is authored by the owner (CLAUDE.md). The script takes the
    identity from main's last commit rather than inventing one, and the message names the run."""
    origin, clone = world
    _night(clone, "20260912T040000Z")

    _record(clone, "nightly-results", "eval-nightly run 99")

    author = _git(origin, "log", "-1", "--format=%an <%ae>", "nightly-results")
    assert author == f"{OWNER[0]} <{OWNER[1]}>"
    message = _git(origin, "log", "-1", "--format=%B", "nightly-results")
    assert message.startswith("eval-nightly run 99: 1 run directory recorded")
    assert "20260912T040000Z-cart-bad-image-tag" in message
    assert "not a finding" in message
    for forbidden in ("Co-Authored-By", "Generated with", "anthropic.com"):
        assert forbidden not in message


def test_a_second_night_appends_and_stays_on_top_of_main(world: tuple[Path, Path]) -> None:
    """The branch accumulates nights until the owner merges it; each night is one commit, and
    the branch keeps main as an ancestor so the pull request is only the unmerged nights."""
    origin, clone = world
    _night(clone, "20260912T040000Z")
    assert _record(clone).returncode == 0

    # Main moves on in the meantime.
    other = clone.parent / "other"
    _git(clone.parent, "clone", "-q", str(origin), str(other))
    (other / "README.md").write_text("moved\n")
    _git(other, "add", "-A")
    _git(other, "commit", "-q", "-m", "something else (#2)")
    _git(other, "push", "-q", "origin", "main")

    second = _night(clone, "20260913T040000Z", "shipping-wrong-image")
    result = _record(clone, "nightly-results", "eval-nightly run 2")

    assert result.returncode == 0, result.stderr + result.stdout
    files = _git(origin, "ls-tree", "-r", "--name-only", "nightly-results")
    assert "evals/runs/20260912T040000Z-cart-bad-image-tag/manifest.json" in files
    assert f"{second}/manifest.json" in files
    assert "README.md" in files, "the results branch was not brought on top of the new main"
    assert _git(origin, "merge-base", "--is-ancestor", "main", "nightly-results") == ""


def test_a_night_with_nothing_new_records_nothing(world: tuple[Path, Path]) -> None:
    """A night refused at the key, or one that scored nothing, must not produce an empty commit
    or a branch."""
    origin, clone = world

    result = _record(clone)

    assert result.returncode == 0, result.stderr
    assert "nothing to record" in result.stdout
    assert _git(origin, "branch", "--list", "nightly-results") == ""


def test_tracked_files_under_the_runs_tree_are_left_alone(world: tuple[Path, Path]) -> None:
    """INVALID.md and the sweep documents are tracked, hand-written, and not the night's to
    change - even if the job modified them, only new directories travel."""
    origin, clone = world
    (clone / "evals" / "runs" / "INVALID.md").write_text("# modified by the job\n")
    _night(clone, "20260912T040000Z")

    assert _record(clone).returncode == 0

    invalid = _git(origin, "show", "nightly-results:evals/runs/INVALID.md")
    assert invalid == "# tracked"


def test_the_script_is_executable_and_bash_clean() -> None:
    assert os.access(SCRIPT, os.X_OK), "chmod +x scripts/nightly_record.sh"
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
