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

    executor_timeout_seconds: float = 30.0
