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
import json
import random
import time
import urllib.request
from collections.abc import Callable, Sequence
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


# Status codes worth trying again. 529 is Anthropic's "overloaded" - the one that ended a
# registered run at T7.58 and left that arm at n = 2 rather than the n = 3 it had registered.
_TRANSIENT_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})

# Connection and timeout failures carry no status code. Matched by name so this module still
# imports without the optional SDK, which is the same reason `AnthropicModel` imports lazily.
_TRANSIENT_NAMES = frozenset(
    {
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "OverloadedError",
        "RateLimitError",
    }
)


def is_transient(exc: BaseException) -> bool:
    """A failure worth trying again, as opposed to one that will fail identically."""
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status in _TRANSIENT_STATUS
    return type(exc).__name__ in _TRANSIENT_NAMES


@dataclass(frozen=True, slots=True)
class Substitution:
    """A model answered that was not the model asked for. Never silent - see `Resilient`."""

    replaced: str
    answered: str
    after: str


class Resilient:
    """Retries a transient failure on the same model, and substitutes only when told to (T2.5).

    T2.5's deliverable names "provider routing, retries with backoff, timeouts, per-incident
    token/dollar budgets, cost metering" and a gateway "with fallback". Timeouts, budgets and
    cost metering arrived under T3.2 and T3.3. This is the retry and the fallback.

    **Retrying is transparent; substituting is not.** A retry on the same model changes nothing
    anything records: the same model answered, so the trajectory, `model_map` and the freeze all
    stay true. A *substitution* is different. `freeze.model_map()` reads `AgentSettings`, so it
    records the model a run was configured with; `ModelResponse.model` records the model that
    answered. Today those cannot disagree, because nothing substitutes. The moment one does,
    a silent fallback would leave the freeze asserting a model that never ran - which is the
    defect T7.54 found in the world digests, in the freeze table this time.

    So substitutions are recorded on this object, and `fallbacks` is empty by default. A
    fallback model's answer quality has never been measured here; switching to one mid-sweep
    changes what a scored run measures, and that has to be a decision rather than a default.
    See ADR-0031.
    """

    def __init__(
        self,
        primary: LanguageModel,
        fallbacks: Sequence[LanguageModel] = (),
        *,
        attempts: int = 4,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._primary = primary
        self._fallbacks = tuple(fallbacks)
        self._attempts = max(1, attempts)
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._sleep = sleep
        self._jitter = jitter
        self.substitutions: list[Substitution] = []

    @property
    def name(self) -> str:
        """The model asked for. What actually answered is on the response, per role."""
        return self._primary.name

    def _try(self, model: LanguageModel, request: ModelRequest) -> ModelResponse:
        """Full jitter, so a sweep's parallel retries do not re-collide on the same schedule."""
        last: BaseException | None = None
        for attempt in range(self._attempts):
            try:
                return model.complete(request)
            except Exception as exc:
                if not is_transient(exc):
                    raise
                last = exc
                if attempt + 1 < self._attempts:
                    ceiling = min(self._base_delay * 2**attempt, self._max_delay)
                    self._sleep(self._jitter(0.0, ceiling))
        assert last is not None
        raise last

    def complete(self, request: ModelRequest) -> ModelResponse:
        try:
            return self._try(self._primary, request)
        except Exception as exc:
            if not (self._fallbacks and is_transient(exc)):
                raise
            failure = f"{type(exc).__name__}: {exc}"
            for spare in self._fallbacks:
                try:
                    response = self._try(spare, request)
                except Exception:
                    continue
                self.substitutions.append(
                    Substitution(
                        replaced=self._primary.name, answered=response.model, after=failure
                    )
                )
                return response
            raise


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


class OpenAICompatibleModel:
    """Any endpoint speaking OpenAI's chat-completions API: vLLM, Ollama, a gateway, or
    OpenAI itself. **T2.5's self-hosted lane**, and the evidence that `LanguageModel` is a
    seam rather than an Anthropic-shaped hole.

    `urllib` from the standard library rather than a client package, deliberately. The claim
    is that the seam is thin, and a demonstration of thinness that needs a dependency is a
    weaker demonstration. It is also one fewer thing to install on the machine whose entire
    reason for existing is that incident data does not leave its network.

    **Two things do not survive the crossing, and both are recorded rather than shimmed.**
    `effort` is Anthropic's adaptive-thinking control and has no equivalent here, so it is
    dropped; a cross-provider comparison is therefore not comparing equal configurations, and
    any ablation that spans providers has to say so. `tools` are omitted for the same reason -
    tool-calling shapes differ, and a translation layer written speculatively, against no
    caller, is the kind of unused seam this project keeps finding.
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 600.0,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    @property
    def name(self) -> str:
        return self._model

    def complete(self, request: ModelRequest) -> ModelResponse:
        payload = {
            "model": self._model,
            "max_tokens": request.max_tokens,
            "messages": [
                {"role": "system", "content": request.system},
                *request.messages,
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        call = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(call, timeout=self._timeout) as response:
            data: dict[str, Any] = json.loads(response.read())

        choice = data["choices"][0]
        usage = data.get("usage", {})
        return ModelResponse(
            text=choice["message"].get("content") or "",
            model=data.get("model", self._model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            stop_reason=choice.get("finish_reason"),
        )


def build_model(
    name: str, *, provider: str = "anthropic", base_url: str | None = None
) -> LanguageModel:
    """The one place a provider is chosen.

    Roles never see this - they hold a `LanguageModel` and cannot tell which one. That is what
    makes the self-hosted lane a configuration change rather than a rewrite, and it is the
    claim T2.5's deliverable asks to have proven rather than asserted.
    """
    if provider == "anthropic":
        return AnthropicModel(name)
    if provider == "openai-compatible":
        if not base_url:
            raise ValueError("provider 'openai-compatible' needs a base_url")
        return OpenAICompatibleModel(name, base_url)
    raise ValueError(f"unknown provider {provider!r}; expected anthropic or openai-compatible")
