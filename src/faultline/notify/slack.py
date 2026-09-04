"""The incoming webhook: the only thing here that opens a socket (T5.2).

T5.2's note is *"plain incoming-webhook messages"*, and its reason is *"signals 'this lives where
on-call actually lives' at **near-zero cost**; full Slack-app interactivity is explicitly out of
scope."* Taken literally: this is one `POST` of one JSON object over `urllib.request`, and it adds
**no dependency at all**. `httpx` is a dev-group package here, not a runtime one, and a task whose
stated value is near-zero cost should not be the reason a clean clone resolves a bigger
environment - which is precisely what T5.4's clean-clone rehearsal exists to catch.

## A webhook URL is a credential, and the standard library leaks it into logs

`https://hooks.slack.com/services/T…/B…/…` is a bearer token wearing a URL's clothes: anyone
holding it can post to the channel as this integration. It gets the same handling as the model key
- `SecretStr`, sourced from the environment, never written to a file and never printed.

**That is not sufficient on its own, and the reason is not obvious.** HTTP client libraries put the
request URL into their exception messages. `requests.HTTPError` and `httpx.HTTPStatusError` both
render as `… for url 'https://hooks.slack.com/services/…'`, so the ordinary act of logging a failed
notification writes the live credential into the log - and a *revoked* webhook, the case most
likely to fail, is the case most likely to be logged. `urllib`'s `HTTPError` happens not to include
the URL today, which is a fact about one standard-library `__str__` and not a property anything
here should rest on.

So every string this module produces goes through `scrub()`, and a test asserts the URL is absent
from the failure path rather than trusting that it never gets there.

## Plaintext transport is refused, not downgraded

A credential sent over `http://` is a credential handed to anything on the path. `SlackWebhook`
raises on a URL that is neither `https` nor loopback rather than sending anyway - and
`from_settings` turns that raise into a `Silent` notifier, because a misconfigured notification
must not stop the consumer loop that consumes alerts.

Loopback is allowed deliberately: it never leaves the machine, and it is what lets the tests
exercise the real class against a real socket instead of a mock of one.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from faultline.notify.announce import Announcer, Delivery, Silent
from faultline.notify.settings import NotifySettings

log = logging.getLogger("faultline.notify")

WEBHOOK_PATTERN = re.compile(r"https?://[^\s'\"]*hooks\.slack\.com[^\s'\"]*", re.IGNORECASE)
"""A second net under the exact-substring replacement in `scrub`.

The first catches the URL this notifier holds. This catches one it does not - a proxy quoting a
different webhook back, or a redirect target - which the exact match cannot see.
"""

REDACTED = "[webhook url redacted]"

LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})
"""Where `http://` is allowed: a request that never leaves the machine cannot leak the credential
in transit. Everything else must be `https`."""

REASON_LIMIT = 300
"""How much of a transport failure is kept. Slack's webhook errors are short strings
(`invalid_payload`, `channel_not_found`) and worth keeping verbatim; an HTML error page from a
proxy in front of it is not, and a log line is not a place to put one."""

NOT_CONFIGURED = (
    "no Slack webhook is configured (set FAULTLINE_NOTIFY_SLACK_WEBHOOK_URL); T5.2's "
    "notifications are off"
)


class InsecureWebhookError(ValueError):
    """A webhook URL that would put a bearer credential on the wire in plaintext."""


def scrub(text: str, url: str) -> str:
    """`text` with any webhook URL removed. **Applied to every string this module returns.**"""
    cleaned = text.replace(url, REDACTED) if url else text
    return WEBHOOK_PATTERN.sub(REDACTED, cleaned)


def transport_is_safe(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme == "https":
        return True
    return parts.scheme == "http" and (parts.hostname or "") in LOOPBACK


@dataclass(frozen=True, slots=True, init=False)
class SlackWebhook:
    """One incoming webhook. Holds a credential, so it renders as one."""

    _url: str
    _timeout: float

    def __init__(self, url: str, timeout: float = 5.0) -> None:
        if not transport_is_safe(url):
            raise InsecureWebhookError(
                "a Slack webhook URL is a bearer credential and this one is not https "
                "(loopback excepted), so sending to it would hand the credential to anything "
                "on the path"
            )
        object.__setattr__(self, "_url", url)
        object.__setattr__(self, "_timeout", timeout)

    def __repr__(self) -> str:
        """**Not the default.** A frozen dataclass renders its fields, and this one's first field
        is the credential - so a bare `print(notifier)` or a traceback frame would publish it."""
        return f"SlackWebhook(url={REDACTED}, timeout={self._timeout})"

    def send(self, text: str) -> Delivery:
        """POST `{"text": ...}`. **Returns a failure; never raises one** - see `announce`."""
        # The scheme is checked in `__init__`, which is why this can be a bare `Request`: a URL
        # that reached here is https or loopback.
        request = urllib.request.Request(
            self._url,
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return Delivery(sent=True, status=int(response.status))
        except urllib.error.HTTPError as refusal:
            return Delivery(
                sent=False,
                status=int(refusal.code),
                reason=self._reason(f"HTTP {refusal.code}: {_body(refusal)}"),
            )
        except Exception as failure:
            # Broad on purpose: a timeout, a DNS failure and a torn socket are all the same thing
            # to a caller holding an incident, and none of them may become its problem. `Exception`
            # rather than `BaseException` - see `announce.Announcer._send`.
            return Delivery(sent=False, reason=self._reason(f"{type(failure).__name__}: {failure}"))

    def _reason(self, text: str) -> str:
        return scrub(" ".join(text.split()), self._url)[:REASON_LIMIT]


def _body(refusal: urllib.error.HTTPError) -> str:
    try:
        return refusal.read().decode("utf-8", "replace")
    except Exception:  # a body that will not read is not worth raising over
        return "(no body)"


def from_settings(settings: NotifySettings | None = None) -> Announcer:
    """The notifier this deployment has, or a `Silent` one that says why it is silent.

    **Every misconfiguration lands here rather than at an incident.** An unset webhook, a
    plaintext one, a base URL that is not a URL - each produces a working `Announcer` that sends
    nothing and one log line at startup. The alternative is a consumer loop that will not start,
    or worse one that dies on its first incident, over a notification setting.
    """
    settings = settings or NotifySettings()
    url = settings.slack_webhook_url.get_secret_value().strip()
    base_url = settings.public_base_url.strip()

    if not url:
        log.info(NOT_CONFIGURED)
        return Announcer(notifier=Silent(NOT_CONFIGURED), base_url=base_url)
    try:
        webhook = SlackWebhook(url, settings.timeout_seconds)
    except InsecureWebhookError as refusal:
        log.warning("Slack notifications are off: %s", refusal)
        return Announcer(notifier=Silent(str(refusal)), base_url=base_url)
    if not base_url:
        # Half of *"with links into the UI"*. Said once here as well as in every message, because
        # the person who can fix it reads logs and the person who needs the link reads Slack.
        log.warning(
            "Slack notifications are on but FAULTLINE_NOTIFY_PUBLIC_BASE_URL is unset, so no "
            "message can link into the UI"
        )
    return Announcer(notifier=webhook, base_url=base_url)
