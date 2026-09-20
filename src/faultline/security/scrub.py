"""Secret scrubbing in front of every model call (T6.8).

The briefing a model receives is built from the world's telemetry - log lines, environment
variables in change records, span attributes - and the world is the threat model's compromised
party (thesis 1). A log line that carries a bearer token, a `postgres://user:pass@` DSN or an AWS
key went to the provider verbatim until this module, and the provider is the one party in the
system this repository has decided not to reason about (THREAT-MODEL, out of scope). What the
platform can do is not hand it what it does not need.

**One table, one function, one call site.** `scrub()` replaces every match of `PATTERNS` with a
typed marker - `[redacted:aws-key]` - so the model still sees *that* a credential was there, which
is evidence (a password in a log line is a finding), without seeing *what* it was. It runs in
`agents.roles.ask`, immediately before `model.complete`, on the system prompt and on every message:
the one place a briefing leaves the process. The count comes back on the `Completion`, is written to
the trajectory step, and is the number the evidence directory reports.

**Not applied to what the trajectory stores.** `trajectory_tool_calls.envelope` is the record of
what the world said, behind the platform's own credential, and an operator who finds a password in
a log line wants to know which one. Rewriting the record to hide the thing it exists to show would
be the wrong scrubber in the wrong place.

**The same table scans the tree** (`tests/test_secret_scanner.py`): a committed credential of any
of these shapes fails CI, which is the *secrets tidy-up* clause with a test instead of a promise.
The patterns are deliberately conservative - a marker where there was no secret costs the model a
token of context; a secret where there should have been a marker costs the thing this module is
for - and every kind is named so a false positive can be read off the step that recorded it.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

MARKER = "[redacted:{kind}]"

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # A PEM block first, because its body would otherwise match the base64-shaped patterns below
    # piecemeal and leave a redacted key with unredacted lines in it.
    (
        "private-key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL
        ),
    ),
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    (
        "slack-webhook",
        re.compile(r"https://hooks\.slack\.com/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]+"),
    ),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    # `scheme://user:password@host` - the password only; the user and host are evidence.
    ("url-credential", re.compile(r"(?<=://)([^\s/:@]+):([^\s/@]+)(?=@)")),
    # `password=hunter22`, `api_key: abc…`, `SECRET="…"`. The key is kept and the value goes,
    # because *which* variable carried a secret is the finding. The value must be eight
    # characters or more **and carry a digit**: `token=1` is a flag, `token: refused` is a log
    # line, `${POSTGRES_PASSWORD:?set it}` is a compose file, and a generated credential without a
    # digit in it is rare enough that the false negative is the cheaper mistake.
    (
        "assignment",
        re.compile(
            r"(?i)\b((?:[a-z0-9.-]*[_.-])?(?:password|passwd|pwd|secret|api[_-]?key|"
            r"access[_-]?key|auth[_-]?token|token)\s*[=:]\s*[\"']?)"
            r"((?=[^\s\"'&,;]*\d)[^\s\"'&,;]{8,})"
        ),
    ),
)
"""In the order applied. `tests/test_scrub.py` holds one positive and one negative per kind."""

KINDS: tuple[str, ...] = tuple(kind for kind, _ in PATTERNS)

TREE_KINDS: frozenset[str] = frozenset(KINDS) - {"assignment", "bearer"}
"""The kinds the tree scanner (`tests/test_secret_scanner.py`) fails CI on: the ones whose match is
a credential's own shape. `assignment` and `bearer` are right in a briefing, where a false positive
costs a marker, and wrong over source code, where `password = os.environ.get(...)` is the line that
*reads* the secret. The scanner reports those two and fails on the rest."""


@dataclass(frozen=True, slots=True)
class Scrubbed:
    text: str
    by_kind: dict[str, int] = field(default_factory=dict)

    @property
    def redactions(self) -> int:
        return sum(self.by_kind.values())


def scrub(text: str) -> Scrubbed:
    """Replace every secret-shaped span in `text` with its typed marker, counting by kind."""
    counts: Counter[str] = Counter()
    for kind, pattern in PATTERNS:
        marker = MARKER.format(kind=kind)
        if kind == "url-credential":

            def keep_user(match: re.Match[str], marker: str = marker) -> str:
                return f"{match.group(1)}:{marker}"

            text, n = pattern.subn(keep_user, text)
        elif kind == "assignment":

            def keep_key(match: re.Match[str], marker: str = marker) -> str:
                return f"{match.group(1)}{marker}"

            text, n = pattern.subn(keep_key, text)
        else:
            text, n = pattern.subn(marker, text)
        if n:
            counts[kind] += n
    return Scrubbed(text, dict(counts))


def findings(text: str) -> list[tuple[str, int]]:
    """Every match as `(kind, line number)`, for the tree scanner - which wants to say where."""
    found: list[tuple[str, int]] = []
    for kind, pattern in PATTERNS:
        for match in pattern.finditer(text):
            found.append((kind, text.count("\n", 0, match.start()) + 1))
    return sorted(found, key=lambda item: item[1])
