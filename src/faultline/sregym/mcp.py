"""A minimal MCP client over SSE, for SREGym's five servers (T7.2, ADR-0044).

SREGym mounts each server at `{MCP_SERVER_URL}/{server}/sse` (`mcp_server/sregym_mcp_server.py`):
`prometheus`, `loki`, `jaeger`, `kubectl` and `submit`. The transport is MCP's original HTTP+SSE:

1. `GET .../sse` opens an event stream whose first event, `endpoint`, names where to POST;
2. JSON-RPC requests are POSTed there and answered **on the stream**, not in the POST's reply;
3. `initialize`, then the `notifications/initialized` notification, then `tools/call`.

**Standard library only, and that is deliberate.** The official SDK would be one more optional
dependency, and its lock entry could not be resolved from where this was built. The protocol
surface used here is four messages, and the tests drive it against a local fake server. Inside
SREGym's box the requests go through its egress proxy because `urllib` honours `HTTP_PROXY`, and
the proxy streams every response (`docker/egress_proxy.py`, `responseheaders`).

**One session per call.** A session costs a GET and three POSTs, about a millisecond each through
the proxy (stage 0's E: 61 ms for 50 round trips), against tool calls that take seconds. A
long-lived session would be a reader thread to keep alive across a whole investigation for no
measurable gain. **That held only once closing stopped waiting on the server**: until the pilot
found it, every session cost one of the server's 15 s keep-alive intervals (`McpSession.__exit__`).
"""

from __future__ import annotations

import ast
import contextlib
import json
import socket
import threading
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import urlsplit

PROTOCOL_VERSION = "2024-11-05"
"""The HTTP+SSE transport's protocol version. SREGym's `fastmcp` server accepts it."""

CLIENT_INFO = {"name": "faultline", "version": "0.0.1"}

SERVERS = frozenset({"prometheus", "loki", "jaeger", "kubectl", "submit"})


class McpError(RuntimeError):
    """The server, the transport or the tool failed. The message says which."""


def _events(lines: Iterator[bytes]) -> Iterator[tuple[str, str]]:
    """Server-sent events as `(event, data)`, per the SSE format: blank line ends an event."""
    event, data = "message", list[str]()
    for raw in lines:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            if data:
                yield event, "\n".join(data)
            event, data = "message", list[str]()
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "event":
            event = value
        elif field == "data":
            data.append(value)


def endpoint_url(base_url: str, server: str, data: str) -> str:
    """Where to POST, from the `endpoint` event.

    Servers differ on whether the path they announce includes the mount point (`/loki/messages/`)
    or is relative to it (`/messages/`). Both are accepted, so a server upgrade on either side
    cannot silently send requests to the wrong mount.
    """
    if data.startswith(("http://", "https://")):
        return data
    root = base_url.rstrip("/")
    if data.startswith(f"/{server}/"):
        return root + data
    if data.startswith("/"):
        return f"{root}/{server}{data}"
    return f"{root}/{server}/{data}"


def _socket_of(stream: Any) -> socket.socket | None:
    """The socket under an `urlopen` response (`HTTPResponse.fp` is a buffered `SocketIO`)."""
    raw = getattr(getattr(stream, "fp", None), "raw", None)
    sock = getattr(raw, "_sock", None)
    return sock if isinstance(sock, socket.socket) else None


def _close_quietly(stream: Any) -> None:
    with contextlib.suppress(Exception):
        stream.close()


class McpSession:
    """One SSE session against one server. Use as a context manager."""

    def __init__(
        self,
        base_url: str,
        server: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 120.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        if server not in SERVERS:
            raise McpError(f"unknown SREGym MCP server {server!r}; known: {sorted(SERVERS)}")
        self._base = base_url
        self._server = server
        self._headers = dict(headers or {})
        self._timeout = timeout
        self._open = opener or urllib.request.urlopen
        self._stream: Any = None
        self._post_url = ""
        self._replies: dict[int, dict[str, Any]] = {}
        self._failure: str | None = None
        self._arrived = threading.Condition()
        self._next_id = 0

    # --- lifecycle -------------------------------------------------------------

    def __enter__(self) -> McpSession:
        url = f"{self._base.rstrip('/')}/{self._server}/sse"
        request = urllib.request.Request(
            url, headers={**self._headers, "Accept": "text/event-stream"}
        )
        try:
            self._stream = self._open(request, timeout=self._timeout)
        except Exception as exc:
            raise McpError(f"{self._server}: could not open {url}: {exc}") from exc
        events = _events(iter(self._stream.readline, b""))
        for event, data in events:
            if event == "endpoint":
                self._post_url = endpoint_url(self._base, self._server, data)
                break
        else:
            raise McpError(f"{self._server}: the stream closed before announcing an endpoint")
        threading.Thread(target=self._read, args=(events,), daemon=True).start()
        self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the stream **without waiting on the server**.

        The reader thread is blocked in `readline` holding the response buffer's lock, and
        closing the response needs that lock. So a plain `close()` waits until the next byte
        arrives, which is the server's keep-alive: **every 15 s in SREGym's `fastmcp` server**.
        That was the pilot's 15.0-15.4 s on every tool call (adapter registration, Addendum 4,
        F3), reproduced offline at the keep-alive's interval. Shutting the socket down first
        returns the reader at once. If the socket cannot be reached, the close is left to a
        daemon thread, so a call never waits on it.
        """
        stream, self._stream = self._stream, None
        if stream is None:
            return
        sock = _socket_of(stream)
        if sock is None:
            threading.Thread(target=_close_quietly, args=(stream,), daemon=True).start()
            return
        with contextlib.suppress(OSError):
            sock.shutdown(socket.SHUT_RDWR)
        _close_quietly(stream)

    # --- the reader --------------------------------------------------------------

    def _read(self, events: Iterator[tuple[str, str]]) -> None:
        try:
            for event, data in events:
                if event != "message":
                    continue
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if isinstance(message, dict) and isinstance(message.get("id"), int):
                    with self._arrived:
                        self._replies[message["id"]] = message
                        self._arrived.notify_all()
            reason = "the stream closed"
        except Exception as exc:  # pragma: no cover - a socket error mid-read
            reason = f"the stream failed: {exc}"
        with self._arrived:
            self._failure = reason
            self._arrived.notify_all()

    # --- requests ----------------------------------------------------------------

    def _post(self, message: dict[str, Any]) -> None:
        request = urllib.request.Request(
            self._post_url,
            data=json.dumps(message).encode(),
            headers={**self._headers, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._open(request, timeout=self._timeout) as reply:
                reply.read()
        except Exception as exc:
            raise McpError(f"{self._server}: POST {message.get('method')} failed: {exc}") from exc

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        ident = self._next_id
        self._post({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        with self._arrived:
            arrived = self._arrived.wait_for(
                lambda: ident in self._replies or self._failure is not None,
                timeout=self._timeout,
            )
            if ident in self._replies:
                reply = self._replies.pop(ident)
            elif not arrived:
                raise McpError(f"{self._server}: no reply to {method} in {self._timeout:.0f} s")
            else:
                raise McpError(f"{self._server}: no reply to {method}: {self._failure}")
        if "error" in reply:
            raise McpError(f"{self._server}: {method} returned an error: {reply['error']}")
        result = reply.get("result")
        return result if isinstance(result, dict) else {}

    def call(self, tool: str, arguments: dict[str, Any]) -> str:
        """One tool call. Its text content, joined; an `isError` reply raises."""
        result = self._request("tools/call", {"name": tool, "arguments": arguments})
        text = "\n".join(
            str(part.get("text", ""))
            for part in result.get("content", []) or []
            if isinstance(part, dict) and part.get("type") == "text"
        )
        if result.get("isError"):
            raise McpError(f"{self._server}.{tool} reported an error: {text[:500]}")
        return text


class McpClient:
    """SREGym's MCP servers, one call at a time. The seam the tests substitute at."""

    def __init__(
        self,
        base_url: str,
        *,
        session_id: str = "",
        timeout: float = 120.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self._base = base_url
        self._session_id = session_id
        """Sent as `sregym_ssid`, which SREGym's kubectl server keys its per-session state on
        (`kubectl_mcp_tools.extract_session_id`). Harmless to the other four."""
        self._timeout = timeout
        self._open = opener

    def call(self, server: str, tool: str, arguments: dict[str, Any]) -> str:
        headers = {"sregym_ssid": self._session_id} if self._session_id else {}
        with McpSession(
            self._base, server, headers=headers, timeout=self._timeout, opener=self._open
        ) as session:
            return session.call(tool, arguments)


# --- what the servers return -------------------------------------------------------

ERROR_PREFIXES = ("[prom_mcp] Error", "[loki_mcp] Error", "[ob_mcp] Error", "Query failed:")
"""How SREGym's servers report a failed backend read: as text, in a successful reply. Read from
`mcp_server/*_server.py` at `46c853db`. A reply starting with one of these is an error, never
data."""


def backend_error(text: str) -> str | None:
    """The error a server reported in its text, or `None` if the text is data."""
    stripped = text.strip()
    return stripped if stripped.startswith(ERROR_PREFIXES) else None


def python_literal(text: str) -> Any:
    """A reply that is `str()` of a parsed object: a Python repr, not JSON (the harness read).

    `ast.literal_eval` accepts exactly literals - no names, no calls - so a reply cannot execute
    anything. `"None"` is the servers' own spelling of no data.
    """
    stripped = text.strip()
    if not stripped or stripped == "None":
        return None
    try:
        return ast.literal_eval(stripped)
    except (ValueError, SyntaxError) as exc:
        raise McpError(f"reply is neither data nor a known error: {stripped[:200]!r}") from exc


def host_of(url: str) -> str:
    """For messages: the host a URL names, without credentials."""
    return urlsplit(url).hostname or url
