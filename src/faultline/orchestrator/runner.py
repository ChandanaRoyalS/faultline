"""What advances an admitted incident inside the product (T5.5c, defect twenty-nine).

`Orchestrator._open` admits an incident - `OPEN -> TRIAGING` when the cap has room - and stops.
`models.IncidentState` says so in as many words: the five states from `TRIAGING` to `PROPOSING`
*"are entered by agent outcomes … what advances them is deliberately not decided."* What advanced
them, in every run this repository has recorded, was the **harness**: `evalharness.run` and
`evalharness.demo` wait `SETTLE_AFTER_ALERT_SECONDS` after correlation and invoke
`faultline-investigate <id>` as a subprocess. ADR-0004 keeps the harness outside the product, so
nothing inside the product ever did.

The first live deployment found the consequence. A fault was injected against the world the
deployment watches; the alerts crossed the compose network, the orchestrator opened incident
`0a61d825…` and admitted it, and it sat in `TRIAGING` with *"not yet investigated"* on the public
page while the container holding the key did nothing with it. T5.5b's deviation three - *"the
instance could remember investigations and not produce one"* - had been closed by adding the
orchestrator container, on the assumption that the orchestrator investigates. It correlates.

This module is the runner: it asks the store for `TRIAGING` incidents whose settle window has
elapsed and runs `faultline-investigate` on each, **as the harness does, as a subprocess, with the
same bounds `make eval` passes** - T4.7's configuration, so a live investigation is the same
experiment as a scored one and its cost is the cost already measured. One at a time: the cap is
enforced at admission, and a second concurrent investigation is a measurement nobody has made.

**Off by default, on in the deployment.** A development machine runs `make demo` and `make eval`,
which launch the investigation themselves; a runner active beside them would investigate every
incident twice and bill for both. `faultline-orchestrate --investigate` (or
`FAULTLINE_ORCH_INVESTIGATE=1`) turns it on, and `deploy/compose.yml` is the only place that does.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from faultline.orchestrator.models import Incident
from faultline.orchestrator.rejections import RejectionStore
from faultline.orchestrator.store import IncidentStore

log = logging.getLogger(__name__)

RunCommand = Callable[[Sequence[str]], int]


def _run_subprocess(command: Sequence[str]) -> int:
    """The default: inherit stdout and stderr so the investigation's own narration reaches the
    container log, where an operator reads it."""
    return subprocess.run(list(command), check=False).returncode


PROVIDER_UNAVAILABLE_EXIT = 6
"""`agents.runner.Exit.PROVIDER_UNAVAILABLE`, restated: the orchestrator does not import the
agent runtime (the arrow points the other way), and a test holds the two equal."""


class InvestigationRunner:
    """Turns admitted incidents into investigations, one at a time, after the settle window."""

    def __init__(
        self,
        store: IncidentStore,
        *,
        settle: timedelta,
        command: Sequence[str],
        max_attempts: int = 2,
        run: RunCommand = _run_subprocess,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        rejections: RejectionStore | None = None,
        max_rejections: int = 2,
        trajectories: Any | None = None,
        provider_cooldown_seconds: float = 300.0,
        provider_open_after: int = 2,
    ) -> None:
        self._store = store
        self._trajectories = trajectories
        self._provider_cooldown = provider_cooldown_seconds
        self._provider_open_after = max(1, provider_open_after)
        self._provider_was_open = False
        self.deferred: int = 0
        """Polls on which every due incident was deferred because the provider was open."""
        """A trajectory store with `close_orphans`, or `None`. **The process that kills
        investigations is the process that reconciles them** (Q72's rule): the sweep ran the
        reconciler for the development machine, and nothing ran it on the deployment, where this
        runner's own subprocess is the thing that dies. `faultline-eval-db orphans` by hand had
        to close the 2026-09-19 drill's row; from here on every poll does (T6.7 piece 3b)."""
        self._settle = settle
        self._command = list(command)
        self._max_attempts = max_attempts
        self._run = run
        self._now = now
        self._rejections = rejections
        self._max_rejections = max_rejections
        """**The re-investigation cap** (T6.3, `PREREGISTRATION-T6.3.md` §2.3). Without a ledger
        this runner cannot count rejections, so without one it re-investigates nothing: a loop
        that cannot count its own turns is a loop that does not stop, and this one spends a model
        call per turn."""
        self.attempts: dict[str, int] = {}
        """Per incident, in this process. An investigation that exits before its first state
        transition leaves the incident in TRIAGING, and without this it would be retried on every
        poll forever, billing each time. Two attempts, then it is left where it is and logged - the
        same visibility ADR-0016 asks of `never_started`."""
        self.exit_codes: list[tuple[str, int]] = []
        self._rounds: dict[str, int] = {}
        """Per incident, the rejection count this process last gave a fresh attempt budget to."""

    def due(self) -> list[Incident]:
        """Admitted or rejected, settled, and not yet given up on - oldest first.

        **A rejected incident is due immediately**, with no settle window: the window exists so
        that an incident's alerts stop arriving before an agent reads them, and a rejection
        arrives long after that - what it waits on is a human, who has already acted.
        """
        cutoff = self._now() - self._settle
        admitted = [
            incident
            for incident in self._store.triaging()
            if incident.opened_at is not None and incident.opened_at <= cutoff
        ]
        return [
            incident
            for incident in [*admitted, *self._reinvestigable()]
            if self.attempts.get(incident.id, 0) < self._max_attempts
        ]

    def _reinvestigable(self) -> list[Incident]:
        """Rejected incidents under the cap. Empty without a ledger - see `_max_rejections`.

        **A new rejection is a new round, and a round gets a fresh attempt budget.** `attempts`
        counts runs that may have died before their first transition, so that a broken incident
        is not billed forever; it is not a count of how many times an incident may legitimately
        be investigated. Without this reset an incident whose first investigation used its two
        attempts could never be re-investigated at all, and the cap that governs the loop would
        be the wrong one, silently.
        """
        if self._rejections is None:
            return []
        due: list[Incident] = []
        for incident in self._store.rejected():
            rejections = self._rejections.count(incident.id)
            if rejections >= self._max_rejections:
                continue
            if self._rounds.get(incident.id) != rejections:
                self._rounds[incident.id] = rejections
                self.attempts.pop(incident.id, None)
            due.append(incident)
        return due

    def reconcile_orphans(self) -> list[str]:
        """Close every trajectory row with no outcome older than the ceiling as `orphaned`.

        A killed `faultline-investigate` leaves its row with `outcome IS NULL` (since T6.7 piece
        3b the row exists from the run's first second, so *every* kill leaves one). Named, not
        guessed: twice the wall-clock budget, the same predicate the sweep uses.
        """
        if self._trajectories is None:
            return []
        from faultline.agents.trajectory import orphan_ceiling_seconds

        closed: list[str] = self._trajectories.close_orphans(
            older_than_seconds=orphan_ceiling_seconds()
        )
        if closed:
            log.warning(
                "orphaned %d trajectory row(s) from killed investigations: %s",
                len(closed),
                ", ".join(closed),
            )
        return closed

    def provider_open(self) -> float | None:
        """Seconds until the cross-run breaker half-opens, or `None` when it is closed.

        **The breaker across runs is computed from the record, not kept** (T6.7 piece 5, design
        note §2): the last `provider_open_after` trajectories all ended `provider_unavailable`,
        and the newest of them ended less than `provider_cooldown_seconds` ago. A run's own
        breaker (`Resilient.breakers`) bounds what one run spends on a dead provider; this bounds
        how many runs are started to learn the same thing. Half-open is the first run after the
        cooldown: it either closes the breaker by finishing, or re-opens it by ending the same
        way. No persisted state, so nothing can disagree with the trajectory table.
        """
        if self._trajectories is None:
            return None
        from faultline.agents.investigation import PROVIDER_UNAVAILABLE_OUTCOME

        recent = list(self._trajectories.recent_outcomes(self._provider_open_after))
        if len(recent) < self._provider_open_after:
            return None
        if any(outcome != PROVIDER_UNAVAILABLE_OUTCOME for outcome, _ in recent):
            return None
        ended = [at for _, at in recent if at is not None]
        if not ended:
            return None
        since = (self._now() - max(ended)).total_seconds()
        remaining = self._provider_cooldown - since
        return remaining if remaining > 0 else None

    def run_once(self) -> list[str]:
        """Investigate everything due, sequentially. Returns the incident ids that were run."""
        self.reconcile_orphans()
        ran: list[str] = []
        due = self.due()
        wait = self.provider_open()
        if wait is not None:
            if due:
                self.deferred += 1
            if not self._provider_was_open:
                log.warning(
                    "provider breaker open: the last %d investigations ended provider_unavailable; "
                    "deferring %d due incident(s), trial run in %.0fs",
                    self._provider_open_after,
                    len(due),
                    wait,
                )
            self._provider_was_open = True
            return ran
        if self._provider_was_open:
            log.info("provider breaker half-open: the next investigation is the trial")
            self._provider_was_open = False
        for incident in due:
            self.attempts[incident.id] = self.attempts.get(incident.id, 0) + 1
            log.info("investigating %s (attempt %d)", incident.id, self.attempts[incident.id])
            code = self._run([*self._command, incident.id])
            self.exit_codes.append((incident.id, code))
            if code == PROVIDER_UNAVAILABLE_EXIT:
                # Not the incident's fault and not an attempt against it: the provider was open.
                # The next poll reads the record and defers; the attempt budget is untouched.
                self.attempts[incident.id] -= 1
                log.warning(
                    "faultline-investigate found the provider unavailable for %s", incident.id
                )
            elif code != 0:
                log.warning("faultline-investigate exited %d for %s", code, incident.id)
            ran.append(incident.id)
        return ran

    def run_forever(self, poll_seconds: float) -> None:
        while True:
            try:
                self.run_once()
            except Exception:  # a runner that dies takes every future incident with it
                log.exception("investigation runner: poll failed; will retry")
            time.sleep(poll_seconds)

    def start_in_background(self, poll_seconds: float) -> threading.Thread:
        """Beside the consumer loop, in the same process, so the container that holds the key is
        the container that spends it. Daemon: the consumer loop's exit is the process's exit."""
        thread = threading.Thread(
            target=self.run_forever, args=(poll_seconds,), name="investigation-runner", daemon=True
        )
        thread.start()
        return thread


def investigate_command(settings: Any) -> list[str]:
    """`faultline-investigate` with T4.7's bounds - the ones `make eval` and `make demo` pass."""
    return ["faultline-investigate", *settings.investigate_args]
