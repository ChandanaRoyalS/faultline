"""How the approval surface reaches the executor (T6.3).

**Over HTTP, because they are different processes on purpose.** The executor holds the Docker
socket and the world's compose files; the API process holds neither and must not (ADR-0038 §1,
`tests/test_deploy.py` counts the containers that mount the socket). So the surface cannot call
`Executor.execute` in-process even though the code is importable: importing it would be one
refactor away from a web process with the world's write credential.

The client is deliberately thin - one POST, one JSON body, the audit row back - and it **never
raises for a refusal**, because a refusal is the executor's normal output and the surface has to
show it to the approver. It raises only when the executor could not be reached at all, which is an
operational fault and not an answer about the world.

`urllib` rather than `httpx` or `requests`, matching `notify.slack.SlackWebhook`: one POST to one
configured URL needs no session, no pool and no dependency.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

EXECUTE_PATH = "/execute"
UNREACHABLE = "the executor could not be reached"


class ExecutorUnreachableError(RuntimeError):
    """The request never got an answer. Not a refusal - nothing is known about the world."""


class ExecutorClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        """Thirty seconds: a `docker compose up -d --force-recreate` of one service is the slowest
        thing behind this call, and the executor writes its audit row before it answers. A timeout
        shorter than the action makes the surface report an unreachable executor for an action
        that is running."""

    def execute(self, token: str, *, caller: str) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self._base}{EXECUTE_PATH}",
            data=json.dumps({"token": token, "caller": caller}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = json.loads(response.read().decode() or "{}")
        except urllib.error.HTTPError as failure:
            # The executor answered, and said no at the HTTP layer - a malformed body, most
            # likely. Its text is the operator's best clue and is passed through rather than
            # replaced with a generic message.
            detail = failure.read().decode(errors="replace")[:500]
            raise ExecutorUnreachableError(f"executor returned {failure.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as failure:
            raise ExecutorUnreachableError(f"{UNREACHABLE}: {failure}") from None
        return dict(body)
