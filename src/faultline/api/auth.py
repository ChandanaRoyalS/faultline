"""The credential on the read surface (T5.5, landed with T5.1's mount).

`incidents.py` recorded the gap in its own docstring: the read routes sit on the same
unauthenticated port as `POST /api/v1/alerts`, and **anything reaching that port can read every
incident, every log line the agent quoted, and every query it ran.** That is a wider exposure than
the write path's, because incident data carries the monitored world's telemetry rather than an
alert label.

While nothing served the routes the gap was theoretical. Mounting them makes it real in the same
commit, so the credential lands in the same commit.

## Why the read surface refuses to start without a password, and the write surface does not

**`POST /api/v1/alerts` stays open, deliberately.** Alertmanager sends no signature, no shared
secret and no credential of any kind - measured over the eight deliveries in
`docs/evidence/t2.1-webhook/`. Putting basic auth in front of it would not authenticate anyone; it
would stop Alertmanager posting. That defence is T2.6/T6.8's and needs a different mechanism.

**The read surface has a caller we control** - a browser, driven by a person - so a credential is
available here in a way it is not there. Given that, the only question left is what happens when
the operator does not set one, and there are two answers:

| | consequence |
|---|---|
| mount open, warn in the log | the demo works, the deploy leaks, and the log line is read after |
| **refuse to start** | the operator is told once, at the only moment they can act on it |

The second, which is also what `faultline-eval` does when it is not told whether a run is single or
part of a sweep. **A default that is safe only if someone reads a warning is not a default.**

## `compare_digest`, not `==`

String equality on a secret returns as soon as two bytes differ, and the time it took says how many
matched. `secrets.compare_digest` takes the same time either way. The window is small over a
network and the fix is one import, which is the whole argument.
"""

from __future__ import annotations

import os
import secrets
from typing import cast

from fastapi import Depends, HTTPException, params, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

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


def guard() -> params.Depends:
    """A dependency that admits the configured pair and nothing else.

    Built once at mount time and shared by every read route, so a route added later inherits it by
    construction rather than by the author remembering - the failure mode this whole module exists
    to close is *a surface that was written and never wired*, and a per-route decorator is that
    failure mode with a smaller blast radius.
    """
    expected_user, expected_password = credentials()

    def check(presented: HTTPBasicCredentials = CREDENTIAL) -> str:
        # Both compared, and **both always compared**: returning early on a wrong username would
        # make the username discoverable by timing even though the password is not.
        user_ok = secrets.compare_digest(presented.username, expected_user)
        password_ok = secrets.compare_digest(presented.password, expected_password)
        if not (user_ok and password_ok):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                # Without this header a browser gets a bare 401 and no prompt, and the operator
                # concludes the deployment is broken rather than that it wants a password.
                headers={"WWW-Authenticate": "Basic"},
                detail="not authorised for the incident read surface",
            )
        return presented.username

    # `Depends` is untyped upstream, so mypy sees Any coming back out of a function this module
    # promises returns a dependency. The cast is the promise, made once here rather than at each
    # of the two mount sites.
    return cast(params.Depends, Depends(check))
