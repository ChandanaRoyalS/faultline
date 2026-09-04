"""T5.1's page, rendered in a real browser (T5.1).

**The escaping claim is only worth something if a renderer honours it.** `faultline.api.view`
labels every world-produced string `untrusted`; a label is advice until something obeys it, and
the page is the something. These tests load the page in Chromium against a stub API and check
that a hostile log line arrives as characters rather than as an element.

THREAT-MODEL thesis 1 is about attacker-influenced telemetry reaching a *model*. This is the same
text reaching a *renderer*, and `el.innerHTML = statement` would be an XSS hole fed by the
monitored system's own logs.
"""

from __future__ import annotations

import glob
import json
import threading
import typing
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

PAGE = Path("src/faultline/api/static/incident.html")

CHROME = next(iter(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")), None)

pytestmark = pytest.mark.skipif(
    CHROME is None, reason="no chromium available; the page's escaping is checked in CI's browser"
)

HOSTILE = '<img src=x onerror="window.__pwned=1">'
"""A log line that would execute if the page used `innerHTML`. Written as a real payload rather
than an inert `<b>` so the assertion is about execution, not about angle brackets surviving."""


def payload(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "incident_id": "inc-1",
        "state": "investigating",
        "severity": "critical",
        "opened_at": "2026-09-03T12:00:00+00:00",
        "episodes": [
            {
                "service": "cartservice",
                "alertname": "ServiceHighErrorRate",
                "severity": "critical",
                "starts_at": "2026-09-03T12:00:00+00:00",
            }
        ],
        "trajectory_id": "t-1",
        "timeline": [
            {
                "seq": 1,
                "role": "metrics",
                "kind": "COMPLETION",
                "at": "2026-09-03T12:01:00+00:00",
                "summary": "promql_query on cartservice",
            }
        ],
        "evidence": [
            {
                "role": "logs",
                "cites": [
                    {
                        "result_id": "tr_1",
                        "resolved": True,
                        "tool": "logql_query",
                        "service": "cartservice",
                        "deep_link": "/explore?left=%7B%7D",
                        "window": None,
                        "untrusted": {"query": '{app="cart"}'},
                    },
                    {
                        "result_id": "tr_invented",
                        "resolved": False,
                        "tool": "",
                        "service": "",
                        "deep_link": None,
                        "window": None,
                        "untrusted": {"query": ""},
                    },
                ],
                "untrusted": {"statements": [HOSTILE], "ruled_out": []},
            }
        ],
        "report": {
            "fault_class": "bad_config",
            "remediation_class": "config_revert",
            "service": "cartservice",
            "confidence": "medium",
            "cites": [],
            "alternatives": [],
            "untrusted": {"root_cause": HOSTILE, "reasoning": "r", "open_questions": []},
        },
    }
    body.update(overrides)
    return body


class Stub(HTTPServer):
    """The page under test fetches `/api/v1/incidents/...`; this answers it and serves the file."""

    body: typing.ClassVar[dict[str, Any]] = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            data = json.dumps(self.server.body).encode()  # type: ignore[attr-defined]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        data = PAGE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_: Any) -> None:
        return


def serve(body: dict[str, Any]) -> tuple[Stub, str]:
    server = Stub(("127.0.0.1", 0), Handler)
    server.body = body
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/ui/incidents/inc-1"


def rendered(body: dict[str, Any]) -> tuple[Any, Any]:
    from playwright.sync_api import sync_playwright

    server, url = serve(body)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME)
        page = browser.new_page()
        page.goto(url)
        page.wait_for_selector("#evidence .card", timeout=5000)
        pwned = page.evaluate("() => window.__pwned === 1")
        html = page.content()
        browser.close()
    server.shutdown()
    return pwned, html


# --- the property the whole `untrusted` convention exists for ---------------------------------


def test_a_hostile_log_line_renders_as_characters_and_does_not_execute() -> None:
    """**The label is advice until something obeys it.**

    `<img src=x onerror=...>` in a specialist's statement is a real payload: if the page used
    `innerHTML` anywhere, the browser would create the element, fail to load `x`, and run the
    handler. It renders as text instead.
    """
    pwned, html = rendered(payload())

    assert pwned is False, "the page executed markup that came out of a log line"
    assert "&lt;img" in html, "and the payload is visible as characters, not swallowed"


def test_a_hostile_root_cause_does_not_execute_either() -> None:
    """The verdict's prose is a model's summary of the same untrusted text, so it is untrusted
    too. Checked separately because it renders through a different branch."""
    body = payload()
    body["evidence"][0]["untrusted"]["statements"] = ["ordinary"]

    pwned, _ = rendered(body)

    assert pwned is False


def test_the_page_never_uses_innerhtml() -> None:
    """Structural, and cheap. The browser test proves the payloads in it are safe; this proves
    there is no *other* path into the DOM for a payload nobody thought of.

    **Comments are stripped first, and that is the fifth instance of one mistake today.** The
    first version of this assertion read `"innerHTML" not in source` and failed - on the comment
    at the top of the page *explaining why `innerHTML` is never used*. A fragment of English is
    not a property; the property is about code.
    """
    import re

    source = PAGE.read_text()
    code = re.sub(r"<!--.*?-->", "", source, flags=re.S)
    code = re.sub(r"^\s*//.*$", "", code, flags=re.M)

    for unsafe in ("innerHTML", "insertAdjacentHTML", "document.write", "outerHTML"):
        assert unsafe not in code, f"{unsafe} is a path into the DOM that does not escape"
    assert "innerHTML" in source, "the comment explaining why it is absent is still there"


# --- the citation is the demo's most convincing moment, so it has to work ----------------------


def test_a_resolved_citation_is_a_link_and_an_unresolved_one_is_not() -> None:
    """*"The clickable citation is the demo's most convincing moment."* An unresolvable id must
    not be clickable — a link to nothing is worse than a marked absence."""
    _, html = rendered(payload())

    assert 'href="/explore?left=%7B%7D"' in html
    assert "unresolved · tr_invented" in html
    assert "href" not in html.split("unresolved")[1][:80], "the unresolved cite is not a link"
