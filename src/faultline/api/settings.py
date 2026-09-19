"""What the HTTP surface needs to know about the processes beside it (T6.3)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FAULTLINE_API_", extra="ignore")

    executor_url: str = "http://executor:8100"
    """Where `faultline-execute serve` answers. The compose service name by default, because that
    is where it is on the deployment and a localhost default would work on a laptop and fail in
    the place it matters. **Internal to the compose network**: `deploy/Caddyfile` forwards nothing
    to it, and `tests/test_deploy.py` holds that."""

    executor_timeout_seconds: float = 330.0
    """How long the approve route waits for the executor's answer. **Was 30 s until T6.7**, and
    the executor's one compose command is bounded at `injector.docker.COMMAND_TIMEOUT_SECONDS`
    (300 s): a slow recreate would have timed the approver out at thirty seconds while the action
    went on to complete and write its audit row - a *timed out* on the screen over an action that
    happened. The wait is the command's bound plus thirty seconds for the executor's own
    bookkeeping, so the answer the approver sees is the executor's. `tests/test_timeouts.py`
    holds the ordering."""
