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
from faultline.orchestrator.store import IncidentStore

log = logging.getLogger(__name__)

RunCommand = Callable[[Sequence[str]], int]


def _run_subprocess(command: Sequence[str]) -> int:
    """The default: inherit stdout and stderr so the investigation's own narration reaches the
    container log, where an operator reads it."""
    return subprocess.run(list(command), check=False).returncode


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
    ) -> None:
        self._store = store
        self._settle = settle
        self._command = list(command)
        self._max_attempts = max_attempts
        self._run = run
        self._now = now
        self.attempts: dict[str, int] = {}
        """Per incident, in this process. An investigation that exits before its first state
        transition leaves the incident in TRIAGING, and without this it would be retried on every
        poll forever, billing each time. Two attempts, then it is left where it is and logged - the
        same visibility ADR-0016 asks of `never_started`."""
        self.exit_codes: list[tuple[str, int]] = []

    def due(self) -> list[Incident]:
        """Admitted, settled, and not yet given up on - oldest first."""
        cutoff = self._now() - self._settle
        return [
            incident
            for incident in self._store.triaging()
            if incident.opened_at is not None
            and incident.opened_at <= cutoff
            and self.attempts.get(incident.id, 0) < self._max_attempts
        ]

    def run_once(self) -> list[str]:
        """Investigate everything due, sequentially. Returns the incident ids that were run."""
        ran: list[str] = []
        for incident in self.due():
            self.attempts[incident.id] = self.attempts.get(incident.id, 0) + 1
            log.info("investigating %s (attempt %d)", incident.id, self.attempts[incident.id])
            code = self._run([*self._command, incident.id])
            self.exit_codes.append((incident.id, code))
            if code != 0:
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
