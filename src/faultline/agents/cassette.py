"""Record and replay model calls: T2.6's fixture harness.

The execution plan's T2.6 row: *"the runtime ships a record/replay harness so agents are
unit-tested against recorded LLM fixtures."* Until 2026-10-15 the runtime shipped the deterministic
fake (`model.DeterministicModel`) and scripted fakes in single test files, and no way to capture
what a real model said and play it back - the audit of 2026-10-13 found the gap.

**How it works.** `RecordingModel` wraps any `LanguageModel` and writes every call it makes - the
full request and the response - to a cassette, a JSON file. `ReplayModel` reads a cassette and
answers each request with the response recorded for it, without a network, a key or a bill. A
request the cassette has not seen raises `CassetteMissError` naming the role and the key, because a
replay that invented an answer would be a fake pretending to be a fixture.

**Keyed on the whole request** (system prompt, messages, role, budget, effort, tools), hashed
canonically, with one normalisation: **tool-result ids**. Every envelope's id (`tr_` and twelve
hex digits, `tools.results`) is random per call by design - the closing delimiter carries it, so a
log line cannot forge the end of its own envelope (ADR-0019) - so two runs of the same
investigation never send byte-identical requests. The key replaces each id with its position of
first appearance (`tr#1`, `tr#2`, ...), and a replayed answer has its recorded ids rewritten to
the ids the replaying run actually issued, so a verdict citing `tr#2` cites the replay's second
envelope and passes the citation check.

So a prompt edit, a contract change that alters the rendered schema, or a different evidence board
misses rather than silently replaying an answer to a question that was not asked -
the replay fails exactly where a re-recording is owed. Identical requests made more than once are
answered in the order they were recorded.

**What a cassette holds and does not**: the response's text, model, token counts and stop reason.
Not `ModelResponse.raw`, which is provider-specific and may carry request identifiers; nothing in
a cassette is needed to reproduce a call that `raw` would add.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from faultline.agents.model import LanguageModel, ModelRequest, ModelResponse

FORMAT = "faultline-cassette/1"

TOOL_RESULT_ID = re.compile(r"\btr_[0-9a-f]{12}\b")
"""`tools.results`' envelope id: `tr_` + `secrets.token_hex(6)`."""


def _ids_in_order(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for match in TOOL_RESULT_ID.finditer(text):
        seen.setdefault(match.group(0), None)
    return list(seen)


def _to_placeholders(text: str, ids: list[str]) -> str:
    index = {real: f"tr#{n}" for n, real in enumerate(ids, start=1)}
    return TOOL_RESULT_ID.sub(lambda m: index.get(m.group(0), m.group(0)), text)


def _from_placeholders(text: str, ids: list[str]) -> str:
    return re.sub(
        r"tr#(\d+)",
        lambda m: ids[int(m.group(1)) - 1] if int(m.group(1)) <= len(ids) else m.group(0),
        text,
    )


def request_payload(request: ModelRequest) -> dict[str, Any]:
    """The request as a cassette stores it: everything a model's answer can depend on."""
    return {
        "role": request.role,
        "system": request.system,
        "messages": request.messages,
        "max_tokens": request.max_tokens,
        "effort": request.effort,
        "tools": request.tools,
    }


def _canonical(request: ModelRequest) -> tuple[str, list[str]]:
    raw = json.dumps(request_payload(request), sort_keys=True, default=str)
    ids = _ids_in_order(raw)
    return _to_placeholders(raw, ids), ids


def request_key(request: ModelRequest) -> str:
    """A canonical hash of the request. `sort_keys` and `default=str`, so dict order and a stray
    non-JSON value (a datetime in a message) cannot make one request two keys; tool-result ids
    by position, so the random id one run issued cannot either."""
    return hashlib.sha256(_canonical(request)[0].encode()).hexdigest()


def response_payload(response: ModelResponse) -> dict[str, Any]:
    return {
        "text": response.text,
        "model": response.model,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "stop_reason": response.stop_reason,
    }


class CassetteMissError(LookupError):
    """A replayed request the cassette never recorded (or recorded fewer times than asked)."""


class RecordingModel:
    """Passes every call to `inner` and appends the request and response to `path`.

    The file is rewritten after every call, so an investigation that dies part-way still leaves a
    cassette of everything it got to.
    """

    def __init__(self, inner: LanguageModel, path: Path) -> None:
        self._inner = inner
        self._path = path
        self._entries: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return self._inner.name

    def complete(self, request: ModelRequest) -> ModelResponse:
        response = self._inner.complete(request)
        canonical, ids = _canonical(request)
        answer = response_payload(response)
        answer["text"] = _to_placeholders(answer["text"], ids)
        self._entries.append(
            {
                "key": hashlib.sha256(canonical.encode()).hexdigest(),
                "request": json.loads(canonical),
                "response": answer,
            }
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {"format": FORMAT, "model": self._inner.name, "entries": self._entries},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        return response


class ReplayModel:
    """Answers from a cassette. Never reaches a provider."""

    def __init__(self, path: Path) -> None:
        document = json.loads(path.read_text())
        if document.get("format") != FORMAT:
            raise ValueError(f"{path} is not a {FORMAT} cassette")
        self._name = str(document.get("model") or "replay")
        self._answers: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        self._roles: dict[str, str] = {}
        for entry in document["entries"]:
            self._answers[entry["key"]].append(entry["response"])
            self._roles[entry["key"]] = entry["request"]["role"]
        self.calls: list[ModelRequest] = []

    @property
    def name(self) -> str:
        return self._name

    def remaining(self) -> int:
        """Recorded answers not yet played. Zero after a faithful replay of the whole run."""
        return sum(len(queue) for queue in self._answers.values())

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        canonical, ids = _canonical(request)
        key = hashlib.sha256(canonical.encode()).hexdigest()
        queue = self._answers.get(key)
        if not queue:
            recorded = sorted(set(self._roles.values()))
            raise CassetteMissError(
                f"no recorded answer for a {request.role!r} request (key {key[:12]}); the "
                f"cassette holds {recorded}. The request differs from every recorded one - a "
                "prompt, contract or evidence change - so the cassette needs re-recording."
            )
        answer = queue.popleft()
        return ModelResponse(
            text=_from_placeholders(answer["text"], ids),
            model=answer["model"],
            input_tokens=int(answer["input_tokens"]),
            output_tokens=int(answer["output_tokens"]),
            stop_reason=answer["stop_reason"],
        )
