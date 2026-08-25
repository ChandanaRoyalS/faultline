"""The provider-agnostic model boundary (T3.2, ADR-0020 §1).

ADR-0003 specified every control point the runtime owns and named no model; ADR-0020 named one
and required the boundary. The requirement is inherited rather than preferred: ADR-0004 records
that the benchmark target "routes models through LiteLLM, so any provider works", so T7.2 will
run this against a harness that already treats the model as configuration.

The shape follows the embedder precedent (ADR-0018): a Protocol, a real implementation behind a
lazy import and an optional extra, and a deterministic fake that tests use exclusively.
`tests/conftest.py` makes that exclusive by construction - reaching a real client from a test
raises, the same contract as the subprocess, Redis and Postgres guards.

**The API key is read from the environment and is never a setting.** Not a field with a
default, not a field with `None`, not a value anything in this repo can print. `AgentSettings`
has no key field at all, and the SDK resolves credentials itself.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """One call. Typed because ADR-0003 requires schema-validated I/O at every boundary."""

    system: str
    messages: list[dict[str, Any]]
    role: str
    """Which of the nine roles is asking. Selects the model (see `AgentSettings.model_for`) and
    is recorded on the trajectory step, so a per-role override is visible in the record rather
    than only in the configuration that produced it."""

    max_tokens: int = 16000
    effort: str = "high"
    tools: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """What came back, plus what it cost. Token counts feed ADR-0020 §5's budget."""

    text: str
    model: str
    """The **effective** model, not the configured default. A per-role override that is not
    recorded here would be invisible in the trajectory."""

    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LanguageModel(Protocol):
    """What an agent role calls. The seam the tests substitute at."""

    @property
    def name(self) -> str:
        """Recorded on every trajectory and every response."""

    def complete(self, request: ModelRequest) -> ModelResponse: ...


class DeterministicModel:
    """Same input, same output, forever. **For tests, and not a model.**

    Hashes the request into a short reply so two different prompts give two different answers
    and one prompt always gives the same one. `hashlib`, not `hash()`, whose seed is randomised
    per process - a suite that passed or failed on `PYTHONHASHSEED` would be worse than no
    suite.

    It exists so the agent layer can be tested without a network, a key, or a bill, and so
    `make check` keeps running in under three seconds.
    """

    def __init__(self, name: str = "deterministic-fake", replies: dict[str, str] | None = None):
        self._name = name
        self._replies = replies or {}
        self.calls: list[ModelRequest] = []

    @property
    def name(self) -> str:
        return self._name

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        if request.role in self._replies:
            text = self._replies[request.role]
        else:
            digest = hashlib.sha256((request.system + repr(request.messages)).encode()).hexdigest()[
                :12
            ]
            text = f"[{request.role}] deterministic reply {digest}"
        return ModelResponse(
            text=text,
            model=self._name,
            input_tokens=len(request.system) // 4,
            output_tokens=len(text) // 4,
            stop_reason="end_turn",
        )


class AnthropicModel:
    """The real one. **Never constructed in a test** - `tests/conftest.py` sees to that.

    The SDK is an optional extra (`faultline[agents]`) imported lazily, so nothing in the agent
    layer loads it until something asks for a completion - the same arrangement the embedding
    model has, and for the same reason.

    Adaptive thinking with `output_config.effort` rather than a fixed thinking budget: the
    budget parameter is removed on the current models, and effort is per-role, because a
    specialist reading one tool result does not need what the synthesizer needs (ADR-0020 §1).
    """

    def __init__(self, model: str, timeout: float = 600.0) -> None:
        self._model = model
        self._timeout = timeout
        self._client: Any | None = None

    @property
    def name(self) -> str:
        return self._model

    def _connect(self) -> Any:  # pragma: no cover - needs the optional dependency and a key
        if self._client is None:
            import anthropic

            # No api_key argument, deliberately: the SDK reads it from the environment, and a
            # key that never passes through this repo's configuration cannot be logged by it.
            self._client = anthropic.Anthropic(timeout=self._timeout)
        return self._client

    def complete(self, request: ModelRequest) -> ModelResponse:  # pragma: no cover - as above
        client = self._connect()
        response = client.messages.create(
            model=self._model,
            max_tokens=request.max_tokens,
            system=request.system,
            messages=request.messages,
            thinking={"type": "adaptive"},
            output_config={"effort": request.effort},
            **({"tools": request.tools} if request.tools else {}),
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return ModelResponse(
            text=text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )
