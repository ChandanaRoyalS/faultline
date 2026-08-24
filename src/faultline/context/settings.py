"""Context-layer configuration (T2.4)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ContextSettings(BaseSettings):
    """Overridable via FAULTLINE_CONTEXT_*."""

    model_config = SettingsConfigDict(
        env_prefix="FAULTLINE_CONTEXT_", env_file=".env", extra="ignore"
    )

    hop_radius: int = 2
    """How far apart two services may be and still be one incident. **Measured, not tuned.**

    Over the 13 nodes and all 78 unordered pairs in the committed snapshot:

    | within | cumulative share of pairs |
    |---|---|
    | 1 hop  | **19%** |
    | 2 hops | **72%** |
    | 3 hops | **97%** |
    | 4 hops | 100% |

    So 1 fails the measured `emailservice` case this policy exists to handle - `cartservice`
    and `emailservice` are two hops apart - and 3 joins 97% of pairs, which is a rule that
    never declines and is `TimeOverlapPolicy` with extra machinery. **2 is the only usable
    value**, and it declines 28% of pairs: a real filter and a thin one, on a graph where
    `checkoutservice` has degree 9 and `frontend` degree 5.

    Anything reporting on correlation quality should quote the 28% rather than describing
    graph-based correlation as precise. Changing this number without re-deriving those
    percentages against the current snapshot is tuning blind.
    """
