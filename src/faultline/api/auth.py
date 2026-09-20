"""The credential on the read surface (T5.5, landed with T5.1's mount).

`incidents.py` recorded the gap in its own docstring: the read routes sit on the same
unauthenticated port as `POST /api/v1/alerts`, and **anything reaching that port can read every
incident, every log line the agent quoted, and every query it ran.** That is a wider exposure than
the write path's, because incident data carries the monitored world's telemetry rather than an
alert label.

While nothing served the routes the gap was theoretical. Mounting them makes it real in the same
commit, so the credential lands in the same commit.

## Why the read surface refuses to start without a password, and the write surface does not

**`POST /api/v1/alerts` stays open by default, deliberately.** Alertmanager sends no signature, no
shared secret and no credential of any kind *unless configured to* - measured over the eight
deliveries in `docs/evidence/t2.1-webhook/`, against a config that configured none. On a
development machine that config is digest-locked, so basic auth in front of the receiver there
would stop Alertmanager posting. A deployment can send the pair, and does (T6.8):
`FAULTLINE_INGEST_REQUIRE_CREDENTIAL=1` and `faultline.ingest.app.credential_gate`, which runs
through this module's `verify`.

**The read surface has a caller we control** - a browser, driven by a person - so a credential is
available here in a way it is not there. Given that, the only question left is what happens when
the operator does not set one, and there are two answers:

| | consequence |
|---|---|
| mount open, warn in the log | the demo works, the deploy leaks, and the log line is read after |
| **refuse to start** | the operator is told once, at the only moment they can act on it |

The second, which is also what `faultline-eval` does when it is not told whether a run is single or
part of a sweep. **A default that is safe only if someone reads a warning is not a default.**

## Ten wrong passwords a minute is a lock-out, not a log line (T6.8)

Nothing limited how fast the credential could be guessed. Caddy logs every request to stdout and
nothing reads that log, so the Caddyfile's own comment - *"the first sign of a credential being
brute-forced is the bill"* - described the detection this deployment actually had. `FailureLimiter`
counts failed credentials per client address: at `LIMIT_FAILURES` inside `LIMIT_WINDOW_SECONDS` the
client is answered **429** for the rest of the window, whatever it presents, and the lock-out is one
`WARNING` line and one count on `/metrics`. In the application rather than in Caddy, for the reason
the Caddyfile gives for basic auth itself: one check, one source of truth.

The client is the **rightmost** `X-Forwarded-For` entry when the header is present - Caddy appends
the peer it saw, so the rightmost is the one a client cannot choose - and the socket peer
otherwise. The table is bounded (`LIMIT_CLIENTS`) so a flood of addresses evicts the oldest rather
than growing the process.

## `compare_digest`, not `==`

String equality on a secret returns as soon as two bytes differ, and the time it took says how many
matched. `secrets.compare_digest` takes the same time either way. The window is small over a
network and the fix is one import, which is the whole argument.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import secrets
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from typing import cast

from fastapi import Depends, HTTPException, Request, params, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

log = logging.getLogger(__name__)

USER_VAR = "FAULTLINE_API_USER"
PASSWORD_VAR = "FAULTLINE_API_PASSWORD"

DEFAULT_USER = "faultline"
"""The username is not the secret and pretending otherwise buys nothing. Overridable anyway,
because an operator who wants two credentials on one deployment should not have to patch this."""

NO_PASSWORD = (
    f"REFUSED: the incident read surface serves every log line and query an investigation "
    f"touched, and {PASSWORD_VAR} is unset. Set it, or start without --postgres-dsn and serve "
    f"the alert receiver alone."
)
"""**Read at startup, not per request.** A process that starts and then refuses every request has
already told the operator the wrong thing: that it is running."""


class UnconfiguredError(RuntimeError):
    """No password is set, so the read surface will not be mounted."""


Unconfigured = UnconfiguredError
"""The name the refusal reads as at a call site: `except auth.Unconfigured`. `UnconfiguredError` is
what the linter's naming rule wants and what a traceback should print, and the two are the same
class, so nothing can catch one and miss the other."""

SCHEME = HTTPBasic(auto_error=True)
"""Module-level, because a `Depends(...)` built in an argument default is re-evaluated per call and
ruff's B008 is right about it. One scheme for the whole surface is also the honest description:
there is one credential, not one per route."""

CREDENTIAL = Depends(SCHEME)


def credentials() -> tuple[str, str]:
    """The configured pair, or `UnconfiguredError`. Never logged, never echoed in an error."""
    password = os.environ.get(PASSWORD_VAR, "")
    if not password:
        raise UnconfiguredError(NO_PASSWORD)
    return os.environ.get(USER_VAR) or DEFAULT_USER, password


LIMIT_FAILURES = 10
"""Failed credentials from one client inside the window before it is locked out."""

LIMIT_WINDOW_SECONDS = 60.0
"""The window, and the length of the lock-out counted from the failure that tripped it."""

LIMIT_CLIENTS = 10_000
"""Distinct client addresses remembered at once. Beyond it the least recently seen is evicted."""

LOCKED_OUT = "too many failed credentials from this address; try again later"


class FailureLimiter:
    """Failed credentials per client, over a sliding window. One per process.

    `blocked(client)` is true while the client's last `limit` failures all fall inside `window`.
    A blocked request records nothing - the lock-out ends `window` after the failure that tripped
    it, not `window` after the last attempt, so a client that keeps hammering is not locked out
    forever. Successes are not counted and do not clear anything: a correct password after nine
    wrong ones is still nine wrong ones.
    """

    def __init__(
        self,
        limit: int = LIMIT_FAILURES,
        window_seconds: float = LIMIT_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        capacity: int = LIMIT_CLIENTS,
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._capacity = capacity
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()
        self.lockouts = 0
        """Lock-outs since the process started; `/metrics` reads it."""

    def _recent(self, client: str) -> deque[float]:
        recent = self._failures.get(client)
        if recent is None:
            recent = deque(maxlen=self.limit)
            self._failures[client] = recent
            while len(self._failures) > self._capacity:
                self._failures.popitem(last=False)
        else:
            self._failures.move_to_end(client)
        cutoff = self._clock() - self.window
        while recent and recent[0] < cutoff:
            recent.popleft()
        return recent

    def blocked(self, client: str) -> bool:
        return len(self._recent(client)) >= self.limit

    def record_failure(self, client: str) -> bool:
        """Count one failure. Returns whether this one tripped the lock-out."""
        recent = self._recent(client)
        recent.append(self._clock())
        if len(recent) >= self.limit:
            self.lockouts += 1
            log.warning(
                "credential lock-out: %d failed credentials from %s inside %.0f s",
                self.limit,
                client,
                self.window,
            )
            return True
        return False


limiter = FailureLimiter()
"""The process's limiter. Module-level because the web process is one process and every route
that checks a credential must count into the same table - two tables would be two budgets."""


def client_of(request: Request) -> str:
    """The client address a failure is counted against. See the module docstring."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        last = forwarded.rsplit(",", 1)[-1].strip()
        if last:
            return last
    return request.client.host if request.client else "unknown"


def matches(presented_user: str, presented_password: str, expected: tuple[str, str]) -> bool:
    """Both compared, and **both always compared**: returning early on a wrong username would make
    the username discoverable by timing even though the password is not."""
    user_ok = secrets.compare_digest(presented_user, expected[0])
    password_ok = secrets.compare_digest(presented_password, expected[1])
    return user_ok and password_ok


def _refuse_locked(retry_after: float) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": str(int(retry_after) or 1)},
        detail=LOCKED_OUT,
    )


def _refuse_credential() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        # Without this header a browser gets a bare 401 and no prompt, and the operator
        # concludes the deployment is broken rather than that it wants a password.
        headers={"WWW-Authenticate": "Basic"},
        detail="not authorised for the incident read surface",
    )


def verify(request: Request, presented: tuple[str, str] | None, expected: tuple[str, str]) -> str:
    """The one check every credentialed route runs: lock-out first, then the pair.

    Returns the username. Raises 429 while the client is locked out - **before** looking at what it
    presented, so a locked-out client learns nothing from a correct guess - and 401 on a wrong or
    missing pair, counting the failure.
    """
    client = client_of(request)
    if limiter.blocked(client):
        raise _refuse_locked(limiter.window)
    if presented is None or not matches(presented[0], presented[1], expected):
        limiter.record_failure(client)
        raise _refuse_credential()
    return presented[0]


def basic_header(request: Request) -> tuple[str, str] | None:
    """The pair in an `Authorization: Basic` header, or `None` when there is no well-formed one.

    Parsed here rather than through `HTTPBasic` so a route can take the credential **without
    declaring a security scheme** in its OpenAPI document - the receiver's committed contract must
    not move when a deployment switches the credential on (`faultline.ingest.app`).
    """
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "basic" or not token:
        return None
    try:
        decoded = base64.b64decode(token.strip(), validate=True).decode()
    except (binascii.Error, UnicodeDecodeError):
        return None
    user, sep, password = decoded.partition(":")
    if not sep:
        return None
    return user, password


def guard() -> params.Depends:
    """A dependency that admits the configured pair and nothing else.

    Built once at mount time and shared by every read route, so a route added later inherits it by
    construction rather than by the author remembering - the failure mode this whole module exists
    to close is *a surface that was written and never wired*, and a per-route decorator is that
    failure mode with a smaller blast radius.
    """
    expected = credentials()

    def check(request: Request, presented: HTTPBasicCredentials = CREDENTIAL) -> str:
        return verify(request, (presented.username, presented.password), expected)

    # `Depends` is untyped upstream, so mypy sees Any coming back out of a function this module
    # promises returns a dependency. The cast is the promise, made once here rather than at each
    # of the two mount sites.
    return cast(params.Depends, Depends(check))
