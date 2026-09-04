"""The seam a notification goes through, and the rule that it never reaches the caller (T5.2).

Nothing in this module knows about HTTP. `faultline.notify.slack` is the only thing that does,
which is what lets the orchestrator's notification path be exercised - including its failure
path - without a socket.

## A notification that fails must not fail the incident

`InvestigationFailedError` records what this costs when it goes wrong: at T3.5's smoke a
`ModuleNotFoundError` raised before the first model call, moved the incident to `FAILED`, and
ADR-0016 makes that state terminal - **one missing optional extra permanently retired a live
incident that nothing had investigated.**

A Slack outage is the same shape and arrives more often. So `Announcer` catches, records and
returns; it never propagates. That is deliberately *two* guards, because they cover different
failures:

- `SlackWebhook.send` returns a `Delivery` rather than raising, which handles the expected ones -
  a timeout, a 404 from a revoked webhook, DNS.
- `Announcer` wraps the call anyway, which handles a `Notifier` implementation that violates the
  protocol's contract. The protocol says "never raises"; the incident machine cannot afford to
  find out that some future implementation disagreed.

The second guard is the one that would look redundant in review. It is the one that matters,
because the first is a promise this module cannot enforce.

## What is deliberately not sent

**Incident resolution.** T5.2's deliverable names two events, *"incident open and report ready"*,
and a resolution is already visible to on-call: Alertmanager sends its own resolved notification
from the same alerts this system consumed. The two events here are the two only Faultline knows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from faultline.notify import messages

log = logging.getLogger("faultline.notify")


@dataclass(frozen=True, slots=True)
class Delivery:
    """What one attempt did. **Never carries the webhook URL** - see `slack.scrub`."""

    sent: bool
    status: int | None = None
    reason: str = ""
    """Why it was not sent, when it was not. Empty on success, and never empty on failure."""


class Notifier(Protocol):
    """One channel a message can go to.

    **The contract is that `send` does not raise.** A caller is an incident state machine or a
    finished investigation, and neither has anything useful to do with a transport error.
    """

    def send(self, text: str) -> Delivery: ...


@dataclass(frozen=True, slots=True)
class Silent:
    """No channel. **A configured absence, not a failure.**

    Carries the reason it is silent so the factory can log it once at startup rather than once per
    incident - a warning repeated per event is a warning nobody reads, and this one is about
    configuration, which does not change between incidents.
    """

    reason: str

    def send(self, text: str) -> Delivery:
        return Delivery(sent=False, reason=self.reason)


@dataclass(slots=True)
class Recorded:
    """Keeps every message instead of sending it. For tests, and for `--dry-run`."""

    messages: list[str] = field(default_factory=list)

    def send(self, text: str) -> Delivery:
        self.messages.append(text)
        return Delivery(sent=True, status=200)


@dataclass(slots=True)
class Raising:
    """A `Notifier` that breaks its own contract. **Exists so the second guard can be tested.**

    A guard against a failure nothing in the tree produces is a guard nobody knows works, which is
    how `no-commit-on-main` came to protect one door of several.
    """

    def send(self, text: str) -> Delivery:
        raise RuntimeError("this notifier violates the protocol's contract")


@dataclass(frozen=True, slots=True)
class Announcer:
    """A notifier and the base URL its links are built from, as one thing to hand to a caller.

    Passed as a unit because the two are useless apart: a notifier with no base URL sends messages
    that cannot reach the UI, which is half of T5.2's deliverable missing, and a base URL with no
    notifier sends nothing.
    """

    notifier: Notifier
    base_url: str = ""

    def incident_opened(self, incident: Any) -> Delivery:
        return self._send(messages.opened(incident, self.base_url), "incident-opened")

    def report_ready(self, incident_id: str, report: Any) -> Delivery:
        return self._send(messages.report_ready(incident_id, report, self.base_url), "report-ready")

    def _send(self, text: str, what: str) -> Delivery:
        try:
            delivery = self.notifier.send(text)
        except Exception as exc:
            # `Exception`, not `BaseException`: a KeyboardInterrupt during a notification is an
            # operator stopping the process, and swallowing it would make the consumer unkillable
            # between events. Same distinction `evalharness.preflight.probe` draws.
            log.warning(
                "the %s notification raised %s; the incident is unaffected",
                what,
                type(exc).__name__,
                exc_info=True,
            )
            return Delivery(sent=False, reason=f"the notifier raised {type(exc).__name__}")
        if not delivery.sent and delivery.reason:
            log.info("no %s notification was sent: %s", what, delivery.reason)
        return delivery


SILENT = Announcer(notifier=Silent("no notifier was configured"))
"""The default everywhere a notifier is optional. **A real object rather than `None`**, so no
caller has to guard a call site - the guard would be the thing that gets forgotten at the third
one."""
