"""Executor configuration. Every field is overridable via FAULTLINE_EXECUTOR_*."""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExecutorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FAULTLINE_EXECUTOR_", env_file=".env", extra="ignore"
    )

    kill_switch: bool = False
    """`FAULTLINE_EXECUTOR_KILL_SWITCH=1` refuses every execution, records the refusal, and
    changes nothing about investigation. **On by default in the deployment** (`deploy/compose.yml`)
    until T6.3 exists: a deployment with an executor and no approval surface has no legitimate path
    to a token, and a switch that is off in that state is a switch nobody would notice being off."""

    token_key: SecretStr = SecretStr("")
    """The HMAC key the mint and the verify share. **Mandatory to mint or verify anything** - an
    empty key refuses rather than signing with nothing, because a token anyone can forge is a
    token that guards nothing. Generate one: `openssl rand -hex 32`. Never in a prompt, never
    logged, never in a token."""

    token_ttl_seconds: int = 900
    """How long an approval stands. Fifteen minutes: long enough to approve and execute by hand,
    short enough that an approval given against one state of the world is not executed against
    another. The proposal's own `confirm_within_seconds` is a different clock - it starts after."""

    postgres_dsn: str = "postgresql://faultline:faultline-dev@localhost:5432/faultline"
    """The platform database: incidents, trajectories, and the append-only `action_audit`."""

    caller: str = "operator"
    """Who is executing, for the audit. The CLI records the operating-system user over this; the
    served endpoint records what T6.3 will pass it."""
