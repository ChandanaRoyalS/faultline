"""The retrieval regression gate (T6.4, `PREREGISTRATION-T6.4.md` §2.4).

**Two numbers with different standing, and this file holds the second one.**

The *floor* — `recall@5 >= 0.60`, `MRR >= 0.45` — was argued before any measurement existed and
**the first measurement missed it** (`evals/runs/RETRIEVAL-2026-09-12-t6.4.md`: 0.465 and 0.219).
That is reported there as the result, with the pipeline called not working. It is deliberately
*not* asserted here: a gate set at a level the pipeline does not reach fails every build and
teaches its reader to ignore it.

The *regression gate* is this file. §2.4: *"set after the first measurement at a stated margin
below it, and labelled in the code as calibrated rather than derived. Its job is to notice change
— a chunking edit, an embedder swap, a corpus addition that dilutes — not to certify quality.
Saying so in the file is the difference between a gate and a decoration."*

**This runs against real pgvector and the real embedder**, because the figure it guards came from
those. A gate over the hashing embedder or the in-memory double would be guarding a different
pipeline and would pass while production regressed.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

from evalharness.retrieval import PREDATES_T6_4, load_golden, measure
from faultline.context.embedding import SentenceTransformerEmbedder
from faultline.context.seed import seed, seed_runbooks
from faultline.context.store import PgVectorPastIncidentStore
from faultline.migrate import upgrade_head

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_ROOT = REPO_ROOT / "evals" / "scenarios" / "artifacts" / "dev"

MEASURED_RECALL_AT_5 = 0.465
MEASURED_MRR_AT_5 = 0.219
"""What the first measurement returned, 2026-09-12, on a one-armed hybrid.

Recorded here so the margin below is readable as a margin rather than as a number someone chose.
"""

GATE_RECALL_AT_5 = 0.40
GATE_MRR_AT_5 = 0.18
"""**Calibrated, not derived.** About 14% and 18% below what was measured.

The margin is not a confidence interval - the golden set is fixed and the corpus is fixed, so
there is no sampling to be noisy about. It is slack for legitimate corpus edits: adding a
document dilutes the pool slightly, and a gate with no slack would fire on every authoring PR and
be disabled within a week.

**It certifies nothing.** Clearing it means retrieval has not got materially worse than a pipeline
already recorded as below its own floor. Q39's fix should move these figures up sharply, and when
it does these constants are re-calibrated *upwards* in the same commit - a regression gate that
stays at the broken pipeline's level after the pipeline is fixed is a decoration again.
"""


@pytest.fixture(scope="module")
def seeded_store() -> Iterator[PgVectorPastIncidentStore]:
    with PostgresContainer("pgvector/pgvector:pg16", driver=None) as container:
        dsn = container.get_connection_url()
        upgrade_head(dsn)
        with psycopg.connect(dsn) as conn:
            store = PgVectorPastIncidentStore(conn, SentenceTransformerEmbedder())
            seed(store, DEV_ROOT)
            seed_runbooks(store)
            conn.commit()
            yield store


def test_the_corpus_ci_seeds_is_the_one_the_measurement_ran_against(
    seeded_store: PgVectorPastIncidentStore,
) -> None:
    """**A freshly seeded corpus, which the measured one was not.**

    `RETRIEVAL-2026-09-12-t6.4.md` §4 records that the machine it ran on held 263 chunks against
    a seed that reported 261 - two orphans from a re-seed that does not reconcile (Q40). This
    container is seeded once from disk, so it has no orphans, and that is a difference worth
    knowing about rather than discovering later as an unexplained drift in the number.
    """
    assert seeded_store.count() > 200


def test_retrieval_has_not_regressed_against_the_calibrated_gate(
    seeded_store: PgVectorPastIncidentStore,
) -> None:
    golden = load_golden()
    result = measure(seeded_store, golden, k=5, predates_task=PREDATES_T6_4)

    assert result.overall.recall_at_k >= GATE_RECALL_AT_5, (
        f"recall@5 {result.overall.recall_at_k:.3f} is below the calibrated gate "
        f"{GATE_RECALL_AT_5}. Measured at {MEASURED_RECALL_AT_5} on 2026-09-12. This gate notices "
        "change; it does not certify quality."
    )
    assert result.overall.mrr >= GATE_MRR_AT_5, (
        f"MRR@5 {result.overall.mrr:.3f} is below the calibrated gate {GATE_MRR_AT_5}. "
        f"Measured at {MEASURED_MRR_AT_5} on 2026-09-12."
    )


def test_the_gate_is_below_the_measurement_and_the_measurement_is_below_the_floor(
    seeded_store: PgVectorPastIncidentStore,
) -> None:
    """The three levels, asserted as an ordering so nobody quietly inverts them.

    A gate above the measurement fails every build. A gate at the registered *floor* would do the
    same, for as long as the pipeline sits under it - which is the situation today and is why the
    floor is a line in a write-up rather than an assertion in CI.
    """
    registered_floor = 0.60
    assert GATE_RECALL_AT_5 < MEASURED_RECALL_AT_5 < registered_floor
