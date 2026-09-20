"""The scrubber in front of every model call (T6.8, `security.scrub`).

One positive and one negative per kind, then the seam: `roles.ask` hands the model a scrubbed
request and reports the count on the `Completion`.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from faultline.agents import roles
from faultline.agents.model import ModelRequest, ModelResponse
from faultline.security import scrub as module
from faultline.security.scrub import KINDS, PATTERNS, TREE_KINDS, Scrubbed, findings, scrub

POSITIVE: dict[str, str] = {
    "private-key": (
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----"
    ),
    "aws-key": "AKIAIOSFODNN7EXAMPLE",
    "anthropic-key": "sk-ant-api03-" + "a" * 40,
    "openai-key": "sk-" + "A1b2" * 10,
    "github-token": "ghp_" + "x" * 36,
    "slack-webhook": "https://hooks.slack.com/services/T000/B000/XXXXXXXXXXXXXXXXXXXX",
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV",
    "bearer": "Authorization: Bearer abcdef0123456789abcdef",
    "url-credential": "postgres://faultline:hunter22@postgres:5432/faultline",
    "assignment": "REDIS_PASSWORD=s3cr3t-value-here",
}

NEGATIVE: dict[str, str] = {
    "private-key": "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----",
    "aws-key": "AKIA-not-a-key",
    "anthropic-key": "sk-ant-short",
    "openai-key": "sk-ant-api03-" + "a" * 40,  # the anthropic shape, claimed by its own kind
    "github-token": "ghp_tooshort",
    "slack-webhook": "https://hooks.slack.com/",
    "jwt": "eyJ.eyJ.sig",
    "bearer": "bearer of bad news",
    "url-credential": "redis://redis-cart:6379/0",
    "assignment": "tokens_in=1234 max_tokens=16000 token=1 token: refused - incident 6871ff51 "
    "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in deploy/.env}",
}


@pytest.mark.parametrize("kind", KINDS)
def test_each_kind_redacts_its_positive(kind: str) -> None:
    result = scrub(f"line before {POSITIVE[kind]} line after")

    assert result.by_kind.get(kind, 0) >= 1, result
    assert f"[redacted:{kind}]" in result.text
    # The secret's own bytes are gone. The url and assignment kinds keep their prefix on purpose.
    secret = POSITIVE[kind]
    if kind == "url-credential":
        secret = "hunter22"
    if kind == "assignment":
        secret = "s3cr3t-value-here"
    assert secret not in result.text


@pytest.mark.parametrize("kind", KINDS)
def test_each_kind_leaves_its_negative_alone(kind: str) -> None:
    result = scrub(NEGATIVE[kind])

    assert result.by_kind.get(kind, 0) == 0, result


def test_the_table_and_the_kinds_agree() -> None:
    assert tuple(kind for kind, _ in PATTERNS) == KINDS
    assert set(POSITIVE) == set(NEGATIVE) == set(KINDS), "every kind has both examples"
    assert set(KINDS) > TREE_KINDS
    assert {"assignment", "bearer"}.isdisjoint(TREE_KINDS)


def test_the_prefix_is_kept_and_the_value_goes() -> None:
    """*Which* variable carried a secret is the finding; the model still sees that."""
    assert scrub("DB_URL=postgres://app:pw12345@db/x").text == (
        "DB_URL=postgres://app:[redacted:url-credential]@db/x"
    )
    assert scrub('api_key: "abcdef123456"').text == 'api_key: "[redacted:assignment]"'
    assert scrub("REDIS_PASSWORD=s3cr3t-value").text == "REDIS_PASSWORD=[redacted:assignment]"


def test_clean_text_is_returned_unchanged_with_a_zero_count() -> None:
    text = "cartservice: Redis connection refused at redis-cart:6379 after 3 retries"
    result = scrub(text)

    assert result == Scrubbed(text, {})
    assert result.redactions == 0


def test_the_count_is_over_every_kind() -> None:
    result = scrub(f"{POSITIVE['aws-key']} then {POSITIVE['aws-key']} and {POSITIVE['jwt']}")

    assert result.redactions == 3
    assert result.by_kind == {"aws-key": 2, "jwt": 1}


def test_findings_name_the_line() -> None:
    text = f"clean\n{POSITIVE['aws-key']}\nclean\n{POSITIVE['github-token']}"

    assert findings(text) == [("aws-key", 2), ("github-token", 4)]


def test_the_module_has_no_dependency_on_the_agents() -> None:
    """The tree scanner imports it from a test that must not need a model client."""
    import inspect

    source = inspect.getsource(module)
    assert "faultline.agents" not in source
    assert "anthropic" not in source.lower().replace("anthropic-key", "")


# --- the seam ------------------------------------------------------------------------------------


class Reply(BaseModel):
    answer: str


class Recording:
    """A model that keeps what it was asked and answers with valid JSON."""

    name = "recording"

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(
            text='{"answer": "ok"}', model=self.name, input_tokens=1, output_tokens=1
        )


def test_ask_hands_the_model_a_scrubbed_request_and_counts_it() -> None:
    model = Recording()
    request = ModelRequest(
        system=f"Rules. Key: {POSITIVE['anthropic-key']}",
        messages=[
            {"role": "user", "content": f"log line: {POSITIVE['url-credential']}"},
            {"role": "user", "content": "clean"},
        ],
        role="test",
    )

    completion = roles.ask(model, request, Reply)

    sent = model.requests[0]
    assert "[redacted:anthropic-key]" in sent.system
    assert "[redacted:url-credential]" in sent.messages[0]["content"]
    assert sent.messages[1]["content"] == "clean"
    assert POSITIVE["anthropic-key"] not in sent.system
    assert "hunter22" not in sent.messages[0]["content"]
    assert completion.redactions == 2
    # The caller's request is not mutated: the record keeps what the world said.
    assert POSITIVE["anthropic-key"] in request.system


def test_a_clean_request_reports_zero() -> None:
    model = Recording()
    completion = roles.ask(
        model,
        ModelRequest(system="Rules.", messages=[{"role": "user", "content": "hi"}], role="t"),
        Reply,
    )

    assert completion.redactions == 0
    assert model.requests[0].system == "Rules."
