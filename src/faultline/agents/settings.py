"""Which model each role uses, and the one thing that is not configurable here (T3.2)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Overridable via FAULTLINE_AGENT_*.

    **There is no API-key field, and its absence is the design.** The SDK resolves credentials
    from the environment; a key that never enters this repo's configuration cannot be written to
    a trajectory, printed by a CLI's `--help`, or committed in a `.env` example. CLAUDE.md's rule
    - secrets never in code or prompts - is easier to keep when there is no field to fill in.
    """

    model_config = SettingsConfigDict(
        env_prefix="FAULTLINE_AGENT_", env_file=".env", extra="ignore"
    )

    model: str = "claude-opus-5"
    """The one default, for every role (ADR-0020 §1)."""

    role_models: dict[str, str] = {}
    """Per-role overrides, empty by default. **This is the decision ADR-0020 left open.**

    One default plus an optional override map, rather than a model named per role: a nine-entry
    table would make nine decisions where the evidence supports one, and ADR-0020 recorded that
    per-role selection should be settled by T4.2's measured accuracy rather than by a cost
    estimate. An empty map is the honest starting state - every role on one model, and any
    departure from that is a deliberate entry someone made.

    **Every published figure reports the effective map, not the default.** A sweep run with
    `{"scribe": "claude-haiku-4-5"}` is not the same experiment as one run without it, and a
    headline that says only `claude-opus-5` would not show the difference.
    """

    effort: str = "high"
    role_efforts: dict[str, str] = {}
    """Same shape, same reason. A specialist reading one tool result does not need what the
    synthesizer needs."""

    judge_model: str = ""
    """**Its own setting, and it inherits nothing** (ADR-0020 §1, decided).

    Empty means unset rather than "same as the agent": defaulting it to whatever the agent runs
    is how the two silently become one model grading its own output, which is ADR-0008's
    judge-contamination axis arriving through a convenience. T4.2 must set it explicitly and
    check the lineage rule at eval time.
    """

    max_tokens: int = 16000
    timeout_seconds: float = 600.0

    def model_for(self, role: str) -> str:
        return self.role_models.get(role, self.model)

    def effort_for(self, role: str) -> str:
        return self.role_efforts.get(role, self.effort)

    def effective_models(self, roles: list[str]) -> dict[str, str]:
        """What every named role would actually run. **This is what a figure reports.**"""
        return {role: self.model_for(role) for role in sorted(roles)}
