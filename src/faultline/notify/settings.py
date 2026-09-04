"""Where notifications go, and under what name this platform is reachable (T5.2)."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class NotifySettings(BaseSettings):
    """Notifier configuration. Every field is overridable via FAULTLINE_NOTIFY_*."""

    model_config = SettingsConfigDict(
        env_prefix="FAULTLINE_NOTIFY_", env_file=".env", extra="ignore"
    )

    slack_webhook_url: SecretStr = SecretStr("")
    """**A bearer credential, not an address.** Anyone holding it can post to the channel as this
    integration, so it gets the same treatment as the model key: sourced from the environment,
    `SecretStr` so an accidental `print(settings)` renders `**********`, and never written to a
    file in this repository.

    Empty by default, and empty is a supported state - `from_settings` returns a notifier that
    sends nothing and says so once."""

    public_base_url: str = ""
    """This platform's externally reachable URL, e.g. `https://faultline.example.com`.

    **There is no default and there cannot be one.** `faultline.api.view` records the same
    constraint for Grafana deep links: *"the platform does not know its own public URL and guessing
    one is how a demo link 404s on a stranger's machine"*. A relative link solved it there because
    the browser had an origin; a Slack message has none, so this is configuration or it is
    nothing. Unset means notifications still send, without a link, saying which variable to set."""

    timeout_seconds: float = 5.0
    """How long a notification may hold up the caller.

    Short deliberately. The caller is either the consumer loop between an incident's durable write
    and its ack, or a finished investigation - and a notification is worth far less than either of
    those completing on time."""
