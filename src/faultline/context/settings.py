"""Context-layer configuration (T2.4)."""

from __future__ import annotations

from typing import Literal

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

    **On v2's graph the shares differ** (Q125, 2026-10-02): 15 nodes, 105 pairs, and within 1, 2,
    3 and 4 hops 19%, **61%**, 90% and 99% (100% at 5). The same holds for astronomy-shop under
    SREGym, whose loaded graph is v2's. So on v2 radius 2 declines **39%** of pairs, and that is
    the figure to quote there. The radius stays 2 for the same reasons: 1 still fails the
    `emailservice`-shaped case and 3 joins 90%.

    **On the DeathStarBench graphs** (Q128): Hotel Reservation, 8 nodes and 28 pairs, 25%, **71%**
    and 100% within 1, 2 and 3 hops; Social Network, 6 nodes and 15 pairs, 53%, **93%** and 100%.
    So on Social Network radius 2 declines 7% of pairs and is close to no filter. Whether the radius
    should differ per application is scoping step 6's question; it is not changed here.
    """

    application: str | None = None
    """**Which foreign application's dependency graph to load**, or none (Q125, ADR-0017).

    Unset - the default, and every run before Q125 - means the graph of the world
    `ToolSettings.world` names, exactly as before. Set, it names an entry of
    `faultline.context.graph.APPLICATIONS` (today only `sregym-astronomy-shop`), and the graph is
    that application's committed snapshot. An unknown name is an error, and so is an application
    whose world differs from `ToolSettings.world`: a graph in one naming scheme and an injector in
    another would disagree silently.

    **Not a world.** The world also selects span-metric names and the container map; an
    application on Kubernetes has neither, which is why this is a setting of its own (the owner's
    decision).
    """

    postgres_dsn: str = "postgresql://faultline:faultline-dev@localhost:5432/faultline"
    """The platform profile's `postgres`, which now runs pgvector (ADR-0018)."""

    embedder: str = "sentence-transformers/all-MiniLM-L6-v2"
    """**Replaceable, and recorded on every chunk so a change is visible in the data.**

    Local rather than an API embedder: a benchmark whose numbers have to be defensible
    cannot have its retrieval depend on a remote model nobody pins, in a project that pins
    its world by content digest. ADR-0018 has the trade-off in full. Installed as
    `faultline[embeddings]` and imported lazily, so `make check` never loads it.
    """

    text_normalisation: int = 0
    """`ts_rank_cd`'s normalisation bitmask for the text arm (Q49, Q53).

    **0 is the standing value and Q49 is why.** Flag 1 moved `recall@3` by zero queries; flag 2
    reaches `recall@5` = 0.605 and clears the registered floor, and Q52's cross-validation showed
    95% of that margin survives selection - but at `k = 3`, the depth production retrieves at,
    choosing among six flags is **worse than not choosing** (out-of-sample -0.0288). So nothing
    was adopted.

    **It is a setting rather than a constant because Q53 has to vary it across a subprocess.**
    `faultline-investigate` runs as a CLI, and the pilot needs one invocation at (0, k=3) and one
    at (2, k=5) against the same incident. A module constant cannot be varied that way without an
    environment hack; a field here can, through `FAULTLINE_CONTEXT_TEXT_NORMALISATION`.

    Making it configurable is not a step toward adopting it. `PREREGISTRATION-Q53.md` adopts
    nothing, and ADR-0041 records that the retrieval side of its rule is already satisfied while
    the evidence that matters - whether a verdict changes - does not exist yet.
    """

    retrieval_mode: Literal["hybrid", "dense"] = "hybrid"
    """**T7.3's E6 switch** (`PREREGISTRATION-T7.3.md`, Addendum 1). `hybrid` is the standing
    pipeline: the dense and text arms fused. `dense` skips the text query and fuses the dense arm
    alone. Read once when the store is built, like `text_normalisation`."""

    rerank_model: str | None = None
    """**T7.3's E7 switch.** Unset, the standing pipeline: no reranking. Set to a cross-encoder's
    name (the registered one is `cross-encoder/ms-marco-MiniLM-L-6-v2`), the store fuses
    `rerank_candidates` candidates and keeps the `k` the cross-encoder scores highest. Local, from
    the embedder's own dependency, so it costs no API money."""

    rerank_candidates: int = 20
    """How many fused candidates the reranker re-scores. Only read when `rerank_model` is set."""

    rerank_revision: str | None = None
    """The cross-encoder's Hugging Face commit, **required whenever `rerank_model` is set**: the
    registration says *revision pinned*, so an unpinned reranker is refused rather than loaded at
    whatever the hub serves that night. Resolved once on the machine that runs the batch and
    recorded in the operation addendum."""

    retrieval_k: int = 3
    """How many chunks a retrieval returns.

    **Was 5, read by nothing, and disagreed with production the whole time** (T6.4 §2.5).
    `Investigation.__init__` and `faultline-investigate` both defaulted to 3 independently, so
    this field described a pipeline nobody ran. A setting that disagrees with production and is
    never consulted is worse than no setting: it is a number a reader will quote.

    It is now 3 - production's value, so nothing changes - and `faultline-investigate` reads it,
    so it is real. That matters beyond tidiness: `retrieval_k` is one of ADR-0018's four
    parameters recorded as *chosen rather than tuned*, and T6.4 built the golden set that can
    finally adjudicate it. A parameter nothing reads cannot be tuned on evidence."""
