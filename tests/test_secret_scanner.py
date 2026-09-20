"""The secrets tidy-up, as a test (T6.8): nothing tracked by git has a credential's shape.

Uses the same table the scrubber applies to briefings (`security.scrub.PATTERNS`), so a shape this
repository refuses to send to a model provider is a shape it refuses to commit. `pre-commit` runs
`detect-private-key`, which is one of the ten kinds; the other nine had nothing.

**Fails on `TREE_KINDS`, reports the rest.** `assignment` (`password=…`) and `bearer` are right in
a log line and wrong over source code, where `password = os.environ.get(...)` is the line that reads
the secret - so they are printed by `test_the_advisory_kinds_are_where_we_think` as a pinned set
rather than failed on, and the set moving is the review.

**The allowlist is two things, both dev-only by construction**: the development Postgres credential
`faultline:faultline-dev@`, which `docker-compose.yml` sets in the clear and THREAT-MODEL's
credentials table records as dev-only, and the test files whose fixtures *are* the positive
examples. Every entry names its reason.
"""

from __future__ import annotations

import functools
import gzip
import subprocess
from pathlib import Path

import pytest

from faultline.security.scrub import PATTERNS, TREE_KINDS

REPO = Path(__file__).resolve().parents[1]

ALLOWED: dict[str, str] = {
    "tests/test_scrub.py": "the positive examples, one per kind - the scanner's own fixtures",
    "tests/test_notify_slack.py": "fabricated hooks.slack.com URLs that the scrubber is tested on",
}
"""Files the tree scanner does not fail on, each with why. **A new entry here is a review.**"""

PLACEHOLDERS = frozenset({"pass", "password", "secret", "pw", "hunter22", "…", "..."})
"""What a docstring writes where a password would go. A `user:pass@host` in prose is the shape
being documented, not a credential; the scrubber still redacts it in a briefing, where it costs a
marker, and the scanner does not fail the tree on it, where it would cost the documentation."""

DEV_CREDENTIAL = "faultline:faultline-dev@"
"""`docker-compose.yml`'s Postgres pair, in the clear on purpose: the development profile, on
localhost, with nothing in it that is not a scenario's telemetry. A deployment supplies its own via
`deploy/.env` (`${POSTGRES_PASSWORD:?…}`), which is gitignored."""

TEXT_SUFFIXES = {
    ".py", ".md", ".yml", ".yaml", ".toml", ".json", ".txt", ".cfg", ".ini", ".sh", ".env",
    ".example", ".log", ".sql", ".html", ".js", ".css", ".conf", ".mako", "",
}  # fmt: skip


def tracked_text_files() -> list[Path]:
    # Tracked files **and untracked ones git would not ignore**: the scan is for the commit
    # about to happen as much as for the ones that did.
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO,
        capture_output=True,
        check=True,
    ).stdout
    files = []
    for name in out.decode().split("\0"):
        if not name:
            continue
        path = REPO / name
        if path.suffix in TEXT_SUFFIXES and path.is_file():
            files.append(path)
    return files


@functools.cache
def scan(kinds: frozenset[str]) -> dict[str, list[tuple[str, int]]]:
    hits: dict[str, list[tuple[str, int]]] = {}
    for path in tracked_text_files():
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        found = []
        for kind, pattern in PATTERNS:
            if kind not in kinds:
                continue
            for match in pattern.finditer(text):
                if kind == "url-credential":
                    span = text[match.start() : match.end() + 1]
                    password = match.group(2)
                    if DEV_CREDENTIAL in span or password in PLACEHOLDERS or "<" in password:
                        continue
                found.append((kind, text.count("\n", 0, match.start()) + 1))
        if found:
            hits[str(path.relative_to(REPO))] = sorted(found, key=lambda item: item[1])
    return hits


def test_nothing_tracked_has_a_credentials_shape() -> None:
    hits = {f: h for f, h in scan(TREE_KINDS).items() if f not in ALLOWED}

    assert hits == {}, "\n".join(f"{f}: {h}" for f, h in hits.items())


def test_the_allowlist_is_still_needed() -> None:
    """An allowlist entry for a file that has no hit is an entry nobody will notice going stale."""
    hits = scan(TREE_KINDS)
    for name, reason in ALLOWED.items():
        assert name in hits, f"{name} is allowed for '{reason}' and has nothing to allow"


@pytest.mark.parametrize("kind", sorted(TREE_KINDS))
def test_every_failing_kind_is_in_the_table(kind: str) -> None:
    assert kind in {k for k, _ in PATTERNS}


def test_no_recorded_capture_carries_a_credential_the_scrubber_would_touch() -> None:
    """Every published figure was measured on briefings built from these captures. The scrubber
    changes a briefing only where it finds a credential shape, so **zero matches over every
    recorded capture, with the full table**, is the statement that no published figure would have
    moved had the scrubber existed - the design note's claim, tested rather than asserted.

    The gzipped captures, because the tree scan above reads text suffixes only; 12.6 MB of the
    world's logs and metrics as of 2026-09-20.
    """
    captures = [
        REPO / name
        for name in subprocess.run(
            ["git", "ls-files", "evals/scenarios/artifacts"],
            cwd=REPO,
            capture_output=True,
            check=True,
            text=True,
        ).stdout.split()
        if name.endswith(".gz")
    ]
    assert captures, "the bundles are in the tree"

    hits: dict[str, list[tuple[str, int]]] = {}
    for path in captures:
        with gzip.open(path, "rt", errors="replace") as handle:
            text = handle.read()
        found = [(kind, len(pattern.findall(text))) for kind, pattern in PATTERNS]
        found = [item for item in found if item[1]]
        if found:
            hits[str(path.relative_to(REPO))] = found

    assert hits == {}, "\n".join(f"{f}: {h}" for f, h in hits.items())
