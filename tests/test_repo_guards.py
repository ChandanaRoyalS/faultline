"""The guards that protect the record, tested rather than trusted (T7.47).

Every rule in this repository that lives only in a hook has the same weakness: a hook is a file
someone can delete, and a hook that guards one entrance is a rule with several doors. Both
failure modes have now happened here, so both are asserted.

**The one that happened.** `no-commit-on-main` guards pre-commit's `pre-commit` stage. `git am`
runs `applypatch-msg`, `pre-applypatch` and `post-applypatch` - never `pre-commit` - so a patch
applied while on main committed and pushed with nothing in its way. That is how B2 (`7fae7b1`)
reached main with no PR. Every patch handed over in this project lands by `git am`, so the hole
had been open for weeks; it only opened *onto main* when a restarted shell left the working tree
there between two steps.

The fix guards the **push** rather than the commit, because the push is where a local mistake
becomes a shared one and because one check there covers every entrance at once - `git am`,
`cherry-pick`, `merge`, `rebase`, and `commit --no-verify` alike. The pre-commit framework has no
`pre-applypatch` stage, so the like-for-like hook was never available; discovering that is what
moved the guard to a better place than the one it was patching.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

CONFIG = Path(".pre-commit-config.yaml")
SCRIPTS = Path("scripts")


def config() -> dict:
    return yaml.safe_load(CONFIG.read_text())


def local_hooks() -> dict[str, dict]:
    hooks: dict[str, dict] = {}
    for repo in config()["repos"]:
        if repo.get("repo") == "local":
            for hook in repo["hooks"]:
                hooks[hook["id"]] = hook
    return hooks


def test_both_entrances_to_main_are_guarded() -> None:
    """**The pair, and why one alone was not enough.**

    The commit guard catches the mistake early and says something useful. The push guard is the
    one that cannot be walked around, because every way of getting a commit onto a branch ends
    at the same push.
    """
    hooks = local_hooks()

    assert "no-commit-on-main" in hooks, "the early, friendly guard"
    assert "no-push-to-main" in hooks, "the one that actually closes the hole"
    assert hooks["no-push-to-main"]["stages"] == ["pre-push"]


def test_the_push_guard_is_installed_by_default_rather_than_remembered() -> None:
    """A hook that only works after someone runs the right `pre-commit install --hook-type`
    incantation is a hook that protects whoever read the README. `default_install_hook_types`
    is what makes it automatic."""
    assert "pre-push" in config()["default_install_hook_types"]


@pytest.mark.parametrize("name", ["no-commit-on-main.sh", "no-push-to-main.sh"])
def test_each_guard_script_exists_and_is_executable(name: str) -> None:
    script = SCRIPTS / name

    assert script.is_file(), f"{name} is referenced by .pre-commit-config.yaml"
    assert os.stat(script).st_mode & stat.S_IXUSR, f"{name} must be executable to run as a hook"


@pytest.mark.parametrize("name", ["no-commit-on-main.sh", "no-push-to-main.sh"])
def test_each_guard_script_is_valid_shell(name: str) -> None:
    """Parsed, not merely present. A guard with a syntax error fails open on some shells and
    noisily on others, and neither is the behaviour it was written for."""
    assert subprocess.run(["bash", "-n", str(SCRIPTS / name)], check=False).returncode == 0


def test_the_push_guard_refuses_on_main_and_allows_everywhere_else() -> None:
    """**Run, not read.** The guard this replaces was correct and still let B2 through, because
    nobody had checked which entrance it stood at. Checking that a script refuses is cheap;
    assuming it does is what this file exists to stop.
    """
    script = (SCRIPTS / "no-push-to-main.sh").resolve()

    def refuses_on(branch: str, tmp: Path) -> bool:
        # A real commit, because `git rev-parse --abbrev-ref HEAD` exits 128 in a repo with
        # none - which makes the guard fail *closed*, the safe direction and the same behaviour
        # `no-commit-on-main.sh` already has. A fixture without a commit would be testing that
        # edge rather than the rule, and nothing can be pushed from an empty repo anyway.
        subprocess.run(["git", "init", "-q", "-b", branch, str(tmp)], check=True)
        (tmp / "seed").write_text("seed\n")
        for command in (
            ["git", "add", "seed"],
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed"],
        ):
            subprocess.run(command, cwd=tmp, check=True)
        result = subprocess.run(
            ["bash", str(script)], cwd=tmp, capture_output=True, text=True, check=False
        )
        return result.returncode != 0

    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        assert refuses_on("main", root / "on-main"), "a push from main must be refused"
        assert not refuses_on("some-task", root / "off-main"), "any other branch must pass"


def test_the_push_guards_claim_about_main_still_holds() -> None:
    """**The comment in the script asserts a fact about this repository's history, so the fact
    is checked.**

    The first draft of that comment claimed *every* commit on main arrives by squash-merge. The
    check falsified it - 24 early commits predate the rule - and the claim was narrowed to the
    last 40, where it is true except for `7fae7b1` itself. A guard justified by a false premise
    is a guard someone is right to delete.
    """
    log = subprocess.run(
        ["git", "log", "--oneline", "-40", "origin/main"],
        capture_output=True,
        text=True,
        check=False,
    )
    if log.returncode != 0 or not log.stdout.strip():
        pytest.skip("no origin/main in this checkout")

    unmerged = [line for line in log.stdout.splitlines() if not line.rstrip().endswith(")")]
    subjects = [line.split(" ", 1)[1] if " " in line else line for line in unmerged]

    assert len(unmerged) <= 1, (
        "more than one recent commit on main did not arrive by squash-merge, so the premise "
        f"the push guard rests on no longer holds: {subjects}"
    )
