"""The webhook, against a real socket - and the credential it must never write down (T5.2).

A local `http.server` rather than a mock of `urlopen`: the properties worth checking are the bytes
on the wire (the JSON body, the content type, the method) and the behaviour of the *actual*
standard-library exception types on a 404 and a timeout. A mock would assert that this module
calls a function, which is not the same claim.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar

import pytest

from faultline.notify import Announcer, Recorded, Silent, announce
from faultline.notify.settings import NotifySettings
from faultline.notify.slack import (
    REDACTED,
    InsecureWebhookError,
    SlackWebhook,
    from_settings,
    scrub,
    transport_is_safe,
)

SECRET_PATH = "/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
"""Shaped like a real webhook path, because the point of these tests is that this string does not
turn up in places it should not."""


class Handler(BaseHTTPRequestHandler):
    received: ClassVar[list[dict[str, Any]]] = []
    status = 200
    body = b"ok"

    def do_POST(self) -> None:  # BaseHTTPRequestHandler's own name; not ours to rename
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        Handler.received.append(
            {"path": self.path, "type": self.headers.get("Content-Type"), "body": raw}
        )
        self.send_response(Handler.status)
        self.send_header("Content-Length", str(len(Handler.body)))
        self.end_headers()
        self.wfile.write(Handler.body)

    def log_message(self, *args: Any) -> None:  # keep the test output readable
        return


@pytest.fixture
def server() -> Any:
    Handler.received = []
    Handler.status = 200
    Handler.body = b"ok"
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}{SECRET_PATH}"
    httpd.shutdown()
    httpd.server_close()


# --- the bytes on the wire --------------------------------------------------------------------


def test_it_posts_one_json_object_with_a_text_field(server: str) -> None:
    """*"Plain incoming-webhook messages"*, taken literally: `{"text": ...}` and nothing else. No
    blocks, no attachments - which is also why the mrkdwn escaping in `messages` is the whole of
    the defence rather than one layer of it."""
    delivery = SlackWebhook(server).send("hello")

    assert delivery.sent and delivery.status == 200
    (sent,) = Handler.received
    assert sent["type"] == "application/json"
    assert json.loads(sent["body"]) == {"text": "hello"}


def test_it_adds_no_runtime_dependency() -> None:
    """*"Near-zero cost"* is T5.2's stated reason for existing. `httpx` is in this repo's dev
    group, not its runtime dependencies, and a task justified by cheapness should not be why a
    clean clone resolves a larger environment - which is exactly what T5.4 rehearses."""
    import faultline.notify.slack as module

    assert module.urllib.request.__name__ == "urllib.request"
    assert not hasattr(module, "httpx") and not hasattr(module, "requests")


# --- the URL is a credential ------------------------------------------------------------------


def test_a_failure_never_reports_the_url(server: str) -> None:
    """**The defect this module exists around.** `requests.HTTPError` and `httpx.HTTPStatusError`
    both render as `… for url '<the webhook>'`, so logging a failed notification writes the live
    credential to disk - and a *revoked* webhook, the case most likely to fail, is the case most
    likely to be logged. `urllib` happens not to today; that is a fact about one `__str__`, not a
    property to rest on."""
    Handler.status = 404
    Handler.body = b"no_service"

    delivery = SlackWebhook(server).send("hello")

    assert not delivery.sent and delivery.status == 404
    assert SECRET_PATH not in delivery.reason
    assert "no_service" in delivery.reason, "Slack's own error text is short and worth keeping"


def test_the_reason_survives_a_body_that_is_not_a_slack_error(server: str) -> None:
    """A proxy in front of the webhook answers with an HTML page. Kept, bounded, on one line."""
    Handler.status = 502
    Handler.body = b"<html>\n<body>Bad Gateway</body>\n</html>" + b" padding" * 200

    delivery = SlackWebhook(server).send("hello")

    assert "\n" not in delivery.reason
    assert len(delivery.reason) <= 300


def test_repr_does_not_publish_the_credential(server: str) -> None:
    """A frozen dataclass renders its fields, and this one's first field is the secret - so the
    default `__repr__` would put it in every traceback frame that mentions the object."""
    rendered = repr(SlackWebhook(server))

    assert SECRET_PATH not in rendered
    assert REDACTED in rendered


def test_scrub_catches_a_webhook_this_notifier_does_not_hold() -> None:
    """The exact-substring replacement can only see its own URL. A redirect target or a proxy
    quoting somebody else's is still a live credential in a log line."""
    other = "https://hooks.slack.com/services/T1/B1/other-secret"

    assert scrub(f"redirected to {other}", "https://hooks.slack.com/services/mine") == (
        f"redirected to {REDACTED}"
    )


def test_the_settings_field_is_a_secret() -> None:
    """So an accidental `print(settings)` renders `**********` rather than the credential - the
    same handling the model key gets."""
    settings = NotifySettings(slack_webhook_url="https://hooks.slack.com/services/T/B/x")  # type: ignore[arg-type]

    assert "hooks.slack.com" not in str(settings)
    assert "**********" in repr(settings)


# --- plaintext is refused, not downgraded -----------------------------------------------------


@pytest.mark.parametrize(
    "url",
    ["http://hooks.slack.com/services/x", "http://10.0.0.5/hook", "ftp://x/y"],
)
def test_a_plaintext_webhook_is_refused(url: str) -> None:
    """A bearer credential over `http://` is a credential handed to anything on the path."""
    with pytest.raises(InsecureWebhookError):
        SlackWebhook(url)


def test_loopback_over_http_is_allowed_deliberately() -> None:
    """It never leaves the machine - and it is what lets these tests drive the real class against
    a real socket rather than a mock of one."""
    assert transport_is_safe("http://127.0.0.1:8080/x")
    assert transport_is_safe("https://hooks.slack.com/services/x")
    assert not transport_is_safe("http://example.com/x")


# --- a notification never fails an incident ---------------------------------------------------


def test_a_notifier_that_breaks_its_contract_does_not_reach_the_caller() -> None:
    """**The guard that looks redundant.** `SlackWebhook.send` returns failures rather than
    raising, so this second guard covers only an implementation that disagrees with the protocol -
    which is the one case the first guard cannot cover, because it is a promise this package
    cannot enforce on somebody else's class.

    What it costs to be wrong is recorded: at T3.5's smoke a `ModuleNotFoundError` before the
    first model call moved a live incident to `FAILED`, which ADR-0016 makes terminal.
    """
    result = Announcer(notifier=announce.Raising()).report_ready("inc-1", object())

    assert result.sent is False
    assert "raised RuntimeError" in result.reason


def test_a_transport_failure_is_a_delivery_and_not_an_exception() -> None:
    """Nothing listening on the port. The expected failure, and the caller is an incident state
    machine between a durable write and an ack."""
    delivery = SlackWebhook("http://127.0.0.1:1/x", timeout=1.0).send("hello")

    assert delivery.sent is False and delivery.reason


def test_silent_is_a_configured_absence_carrying_its_reason() -> None:
    """Not an error, and not `None`. Every optional call site takes an `Announcer`, so no caller
    has to guard - the guard is what gets forgotten at the third one."""
    delivery = Announcer(notifier=Silent("nothing configured")).incident_opened(object())

    assert delivery.sent is False
    assert delivery.reason == "nothing configured"


# --- what a deployment gets -------------------------------------------------------------------


def test_no_webhook_yields_a_working_announcer_that_sends_nothing() -> None:
    announcer = from_settings(NotifySettings(slack_webhook_url="", public_base_url=""))  # type: ignore[arg-type]

    assert announcer.incident_opened(object()).sent is False


def test_a_misconfigured_webhook_never_stops_the_consumer(caplog: Any) -> None:
    """**Every misconfiguration lands in the factory rather than at an incident.** The alternative
    is a consumer loop that will not start, or one that dies on its first incident, over a
    notification setting."""
    announcer = from_settings(
        NotifySettings(slack_webhook_url="http://hooks.slack.com/services/x")  # type: ignore[arg-type]
    )

    assert announcer.incident_opened(object()).sent is False
    assert "not https" in announcer.notifier.reason  # type: ignore[union-attr]


def test_a_configured_webhook_with_no_base_url_warns_once_at_startup(caplog: Any) -> None:
    """Once here, and again in every message. The person who can fix it reads logs; the person who
    needs the link reads Slack."""
    with caplog.at_level("WARNING", logger="faultline.notify"):
        from_settings(
            NotifySettings(slack_webhook_url="https://hooks.slack.com/services/T/B/x")  # type: ignore[arg-type]
        )

    assert "FAULTLINE_NOTIFY_PUBLIC_BASE_URL" in caplog.text


def test_recorded_keeps_messages_for_a_caller_that_wants_to_look() -> None:
    recorder = Recorded()
    Announcer(notifier=recorder, base_url="https://x").report_ready("inc-1", object())

    assert len(recorder.messages) == 1
