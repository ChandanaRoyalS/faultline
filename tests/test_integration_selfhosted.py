"""T2.5's verified self-hosted seam.

The deliverable is *"the seam is proven provider-agnostic against an OpenAI-compatible
endpoint - the self-hosted vLLM lane from the positioning"*. Until now nothing had ever run
against a non-Anthropic endpoint, so provider-agnosticism was an architectural intention.

**What this proves and what it does not.** It proves the seam: a conformant chat-completions
endpoint produces a valid `ModelResponse`, the request carries what the contract says, and the
retry wrapper is indifferent to which implementation it holds. It does **not** prove vLLM
specifically - that needs a GPU-class image and a model download, and a test nobody can run is
worse than one with a stated scope. The endpoint here is a conformant stub, and the difference
is the point of this paragraph.

Marked `integration` because it binds a socket. `make check` is hermetic by contract - no
containers, no network - and loopback is still network.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from faultline.agents.model import (
    ModelRequest,
    OpenAICompatibleModel,
    Resilient,
    build_model,
)

pytestmark = pytest.mark.integration

RECORDED: dict[str, Any] = {}
SERVED_MODEL = "Qwen2.5-32B-Instruct"


class Handler(BaseHTTPRequestHandler):
    """The shape vLLM, Ollama and OpenAI all answer with."""

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        RECORDED["path"] = self.path
        RECORDED["authorization"] = self.headers.get("Authorization")
        RECORDED["body"] = json.loads(self.rfile.read(length))
        body = json.dumps(
            {
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "model": SERVED_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"verdict": "ok"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 41, "completion_tokens": 7, "total_tokens": 48},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        return None


@pytest.fixture
def base_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()


def a_request() -> ModelRequest:
    return ModelRequest(
        system="You are the synthesizer.",
        messages=[{"role": "user", "content": "What broke?"}],
        role="synthesizer",
        max_tokens=512,
    )


def test_a_conformant_endpoint_produces_a_valid_model_response(base_url: str) -> None:
    """Every field of `ModelResponse`, mapped from the OpenAI shape."""
    model = OpenAICompatibleModel("Qwen2.5-32B-Instruct", base_url)

    response = model.complete(a_request())

    assert response.text == '{"verdict": "ok"}'
    assert response.model == SERVED_MODEL
    assert response.input_tokens == 41
    assert response.output_tokens == 7
    assert response.stop_reason == "stop"


def test_the_system_prompt_is_sent_as_the_first_message(base_url: str) -> None:
    """Anthropic takes `system` as its own parameter; OpenAI takes it as a message.

    Getting this wrong would silently drop every role prompt - the model would answer, the
    schema would fail to parse, and it would look like a bad model rather than a lost prompt.
    """
    OpenAICompatibleModel("m", base_url).complete(a_request())

    messages = RECORDED["body"]["messages"]
    assert messages[0] == {"role": "system", "content": "You are the synthesizer."}
    assert messages[1]["content"] == "What broke?"
    assert RECORDED["path"].endswith("/chat/completions")


def test_a_key_is_sent_as_a_bearer_token_and_absence_sends_no_header(base_url: str) -> None:
    OpenAICompatibleModel("m", base_url, api_key="sk-local-abc").complete(a_request())
    assert RECORDED["authorization"] == "Bearer sk-local-abc"

    RECORDED.clear()
    OpenAICompatibleModel("m", base_url).complete(a_request())
    assert RECORDED["authorization"] is None, "a self-hosted endpoint usually needs no key"


def test_the_retry_wrapper_does_not_know_which_provider_it_holds(base_url: str) -> None:
    """`Resilient` is T2.5's other half, and it must be provider-agnostic too - otherwise the
    self-hosted lane would run without the retries the Anthropic lane gets."""
    resilient = Resilient(OpenAICompatibleModel("m", base_url))

    assert resilient.complete(a_request()).text == '{"verdict": "ok"}'


def test_the_provider_is_a_setting_rather_than_a_branch_in_the_agent_code(
    base_url: str,
) -> None:
    """What makes this a lane rather than a fork: one factory, chosen by configuration."""
    model = build_model("m", provider="openai-compatible", base_url=base_url)

    assert model.complete(a_request()).model == SERVED_MODEL

    with pytest.raises(ValueError, match="needs a base_url"):
        build_model("m", provider="openai-compatible")
    with pytest.raises(ValueError, match="unknown provider"):
        build_model("m", provider="bedrock")
