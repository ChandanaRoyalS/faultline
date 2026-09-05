"""The front door names every command that produced a number (T5.4).

T7.46 asked *"can anyone else run this?"* and found the sharpest answer in the negative: **every
figure in README's results section was produced by a command README does not mention.** When this
guard was written the front door named **one of sixteen** console scripts.

That is what "reproducible MVP" fails on. A reader can follow the demo, read the tables, and have
no way to regenerate a single cell — and the one command they might guess at, `faultline-eval`,
refuses with `REFUSED: say whether this is one run or part of a sweep`, a requirement documented
only in `docs/PLAN.md`.

**The guard is coverage, not prose.** It cannot tell whether an entry is any good; it can tell
whether a command exists that the front door never names, which is the failure that actually
happened and the one that comes back the moment a script is added.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"


def console_scripts() -> set[str]:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]
    return set(project.get("scripts", {}))


def test_every_console_script_is_named_in_the_readme() -> None:
    """**README itself, not README plus what it links to.**

    The first version of this guard accepted a command documented in any page README links to,
    on the reasoning that one hop is close enough. It caught **one** of the sixteen — because
    README links to `docs/PLAN.md`, and a 4,000-line task record mentions everything. A guard
    that a link to the task record satisfies is a guard the original defect passes, which is
    the whole thing it was written to fail.

    `docs/PLAN.md` is a record of what was done, not documentation of how to do it. The front
    door names the commands, or a reader does not have them.
    """
    body = README.read_text()

    missing = sorted(name for name in console_scripts() if name not in body)

    assert missing == [], (
        f"{len(missing)} command(s) exist that README never names: {missing}. Every figure "
        "this project publishes came from one of these, and a reader who cannot find the "
        "command cannot reproduce the number."
    )


def test_the_readme_names_the_refusal_a_stranger_will_hit_first() -> None:
    """`faultline-eval` refuses without `--single-run` or `--runs-remaining N`. The refusal message
    is good; its absence from the documentation was the defect T7.46 named."""
    body = README.read_text()

    assert "--single-run" in body
    assert "--runs-remaining" in body


def test_the_scripts_table_is_not_the_only_mention_of_the_scoring_command() -> None:
    """A table row is a listing, not an explanation. The command every published figure came from
    needs the paragraph it already has, and this fails if that paragraph is ever cut down to the
    table entry."""
    body = README.read_text()

    assert "make eval SCENARIO=" in body
    assert "Exit codes:" in body
