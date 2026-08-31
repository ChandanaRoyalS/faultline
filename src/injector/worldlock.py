"""One driver of the world, enforced rather than instructed (T7.37).

**Why this lives in `injector` and not in the harness.** Both world-changing harness paths -
`evalharness.run` (scored runs) and `evalharness.rehearse` (the recorder) - already import from
`injector`, and `injector` imports neither of them. Putting the lock here is what lets both take
the *same* lock; a lock that lived in one of them would be a lock the other route defeats.

**What it covers.** Whole-session exclusivity for the two harness entry points that drive the world,
plus `faultline-inject` when it is not already running underneath one of them.

**What it does not cover, stated plainly rather than implied away.** A shell script that calls
`docker` or `docker compose` directly bypasses this entirely - T7.36's own probe did exactly that,
and so did T7.30's. **Scratch probe scripts cannot be made to take this lock**, because the thing
they have in common with the harness is Docker, not any Python module. The lock makes the *harness*
single-driver; it does not make the *world* single-driver. An operator running a probe by hand is
still the thing that has to know not to.
"""

from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = REPO_ROOT / ".faultline" / "harness.lock"

TOKEN_ENV = "FAULTLINE_WORLD_LOCK_TOKEN"
"""Set by a holder for its children, so a run that shells out to `faultline-inject` is not
locked out by itself. Re-entrancy is by token rather than by pid because the child is a
different process and inherits the environment but not the pid."""


class WorldLockError(RuntimeError):
    """Another driver holds the world. **Nothing was changed.**"""


def _alive(pid: int) -> bool:
    """Whether a pid is still running. A dead holder is reclaimable; a live one is not."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists and belongs to someone else. Alive for our purposes.
        return True
    return True


class WorldLock:
    """Hold the world for one driver. **Does not wait.**

    Waiting on a world lock is how two harness processes interleave injections with nothing in
    either log to show it. An instruction to a human since T3.3, a file since T4.1, and taken by
    only one of the two drivers until T7.37 - the recorder never took it, which is how T7.36 came
    within one sleep of recording a second injection behind a live one.

    **Advisory, and the choice is deliberate.** It refuses by default and can be overridden with
    `force=True`, which is recorded. The operator here is one person who is also the only one who
    can fix a wedged world, so a lock they cannot get past is a lock they will delete by hand in a
    hurry - and a lock cleared by an undocumented incantation is worse than no lock, because the
    next person learns the incantation and not the reason. The override exists, it is a flag rather
    than a `rm`, and every use of it lands in the run record.

    **A dead holder is reclaimed automatically, and the reclaim is recorded.** A stale lock and a
    live one look identical from the outside, which is exactly why the difference has to be written
    down rather than assumed: `info()["reclaimed"]` says a previous holder was found dead and taken
    over, and names it.
    """

    def __init__(self, path: Path = LOCK_PATH, *, reason: str = "", force: bool = False) -> None:
        self._path = path
        self._reason = reason
        self._force = force
        self._token = f"{os.getpid()}-{datetime.now(UTC).timestamp()}"
        self._info: dict[str, Any] = {}
        self._reentrant = False

    # --- reading an existing holder -------------------------------------------------

    def _holder(self) -> dict[str, Any] | None:
        try:
            raw = self._path.read_text()
        except FileNotFoundError:
            return None
        try:
            loaded: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            # A hand-written or truncated lock. Treat it as a holder we cannot identify
            # rather than as absent - refusing is the safe reading.
            return {"pid": None, "since": None, "reason": raw.strip()[:200], "unparseable": True}
        return loaded

    def _record(self) -> dict[str, Any]:
        return {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "since": datetime.now(UTC).isoformat(),
            "reason": self._reason,
            "token": self._token,
        }

    # --- the context manager --------------------------------------------------------

    def __enter__(self) -> WorldLock:
        if os.environ.get(TOKEN_ENV):
            # Already inside a holder - a child shelling out to the injector. Re-entrant by
            # design: the driver that took the lock is the one making this call.
            self._reentrant = True
            self._info = {"held_by_parent": os.environ[TOKEN_ENV], "acquired": False}
            return self

        self._path.parent.mkdir(parents=True, exist_ok=True)
        reclaimed: dict[str, Any] | None = None

        holder = self._holder()
        if holder is not None:
            pid = holder.get("pid")
            live = _alive(int(pid)) if isinstance(pid, int) else True
            if live and not self._force:
                raise WorldLockError(
                    f"another driver holds the world.\n"
                    f"    holder : pid {pid} on {holder.get('host')} since {holder.get('since')}\n"
                    f"    doing  : {holder.get('reason') or 'unspecified'}\n"
                    f"    lock   : {self._path}\n"
                    "**Nothing was changed.** If that process is gone this lock reclaims itself "
                    "automatically - a live holder is one that answers. If you believe the holder "
                    "is wrong, stop it, or re-run with --force-lock, which takes the world and "
                    "records that it did."
                )
            reclaimed = {
                "pid": pid,
                "since": holder.get("since"),
                "reason": holder.get("reason"),
                "was": "forced" if live else "dead",
            }
            self._path.unlink(missing_ok=True)

        record = self._record()
        if reclaimed is not None:
            record["reclaimed"] = reclaimed
        try:
            handle = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:  # pragma: no cover - lost a race with another acquirer
            raise WorldLockError(
                f"lost a race for {self._path}; another driver acquired it first. "
                "Nothing was changed."
            ) from None
        os.write(handle, json.dumps(record, indent=1).encode())
        os.close(handle)
        os.environ[TOKEN_ENV] = self._token
        self._info = {"acquired": True, **record}
        return self

    def __exit__(self, *exc: object) -> None:
        if self._reentrant:
            return
        os.environ.pop(TOKEN_ENV, None)
        holder = self._holder()
        # Only release our own lock. If somebody forced past us, theirs stays.
        if holder is not None and holder.get("token") == self._token:
            self._path.unlink(missing_ok=True)

    # --- what the run record gets ---------------------------------------------------

    def info(self) -> dict[str, Any]:
        """What to write into the manifest. **A reclaim or a force is a fact, not an inference.**

        T7.33 recorded `world_continuity` so that a kafka recycle is a recorded event rather than
        a discontinuity somebody has to notice. A second driver during a recording is the same
        kind of fact and is recorded the same way - with the difference that a *clean* acquisition
        is recorded too, so that a bundle with no `world_lock` block is identifiable as one
        written by a path that does not take the lock at all.
        """
        return dict(self._info)
