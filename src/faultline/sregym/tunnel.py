"""A loopback port that reaches a host port through SREGym's egress proxy, by CONNECT (T7.2).

Inside SREGym's filtered agent container the only route out is its egress proxy, and psycopg
cannot use an HTTP proxy. This listens on a loopback port and, for each connection, asks the proxy
for a CONNECT tunnel to the target and copies bytes both ways. Stage 0 measured it: Postgres with
pgvector through SREGym's own proxy, 50 round trips in 61 ms
(`evals/attempts/T7.2-adapter-stage0/`).
The prototype is `docs/evidence/t7.2-adapter/spike_tunnel.py.txt`; this is the same protocol, as a
class the driver starts and stops.
"""

from __future__ import annotations

import contextlib
import os
import socket
import threading
from urllib.parse import urlsplit


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while chunk := src.recv(65536):
            dst.sendall(chunk)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            with contextlib.suppress(OSError):
                s.shutdown(socket.SHUT_RDWR)


def connect_via_proxy(
    proxy_url: str, target_host: str, target_port: int, timeout: float = 30.0
) -> socket.socket:
    """An open socket to `target_host:target_port`, through the proxy's CONNECT."""
    proxy = urlsplit(proxy_url)
    if not proxy.hostname:
        raise OSError(f"not a proxy URL: {proxy_url!r}")
    upstream = socket.create_connection((proxy.hostname, proxy.port or 8080), timeout=timeout)
    upstream.sendall(
        f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
        f"Host: {target_host}:{target_port}\r\n\r\n".encode()
    )
    reply = b""
    while b"\r\n\r\n" not in reply:
        chunk = upstream.recv(4096)
        if not chunk:
            upstream.close()
            raise OSError("the proxy closed the connection during CONNECT")
        reply += chunk
    status = reply.split(b"\r\n", 1)[0].decode(errors="replace")
    if " 200 " not in f"{status} ":
        upstream.close()
        raise OSError(f"the proxy refused CONNECT: {status}")
    upstream.settimeout(None)
    return upstream


class Tunnel:
    """`127.0.0.1:<port>` -> `target_host:target_port` through `HTTPS_PROXY`."""

    def __init__(
        self,
        target_host: str,
        target_port: int,
        *,
        proxy_url: str | None = None,
        listen_port: int = 0,
    ) -> None:
        self._target = (target_host, target_port)
        self._proxy = proxy_url or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if not self._proxy:
            raise OSError("no HTTPS_PROXY to tunnel through")
        self._server = socket.socket()
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", listen_port))
        self._server.listen(16)
        self.port: int = self._server.getsockname()[1]
        self.failures: list[str] = []
        self._closed = False

    def start(self) -> Tunnel:
        threading.Thread(target=self._serve, daemon=True).start()
        return self

    def _serve(self) -> None:
        assert self._proxy is not None
        while not self._closed:
            try:
                client, _ = self._server.accept()
            except OSError:
                return
            try:
                upstream = connect_via_proxy(self._proxy, *self._target)
            except OSError as exc:
                self.failures.append(str(exc))
                client.close()
                continue
            threading.Thread(target=_pipe, args=(client, upstream), daemon=True).start()
            threading.Thread(target=_pipe, args=(upstream, client), daemon=True).start()

    def stop(self) -> None:
        self._closed = True
        with contextlib.suppress(OSError):
            self._server.close()
