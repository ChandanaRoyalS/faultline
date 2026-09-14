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
from testcontainers.community.postgres import PostgresContainer

from evalharness.retrieval import PREDATES_T6_4, load_golden, measure
from faultline.context.embedding import SentenceTransformerEmbedder
from faultline.context.seed import seed, seed_runbooks
from faultline.context.store import PgVectorPastIncidentStore
from faultline.migrate import upgrade_head

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_ROOT = REPO_ROOT / "evals" / "scenarios" / "artifacts" / "dev"

MEASURED_RECALL_AT_5 = 0.442
MEASURED_MRR_AT_5 = 0.286
"""What the **second** measurement returned, 2026-09-13, on a two-armed hybrid (Q39).

Reported on the **reconciled 261-chunk corpus** (Q48), which is what this container seeds; the
2026-09-13 write-up leads with 0.442 and **0.311** because it ran against a database still holding
two orphan chunks, and removing them cost 8% of `MRR@5` and no recall at all.

The first measurement, on 2026-09-12 with a text arm that matched nothing, returned **0.465 and
0.219**.
`recall@5` therefore went *down* and `MRR@5` went sharply up;
`evals/runs/RETRIEVAL-2026-09-13-q39.md` reports the whole of it, including that the recall
difference is **one query of 43** and that the registered decision rule said not to adopt.

Recorded here so the margin below is readable as a margin rather than as a number someone chose.
"""

GATE_RECALL_AT_5 = 0.40
GATE_MRR_AT_5 = 0.26
"""**Calibrated, not derived.** 9.5% and 9.1% below what was measured.

The margin is not a confidence interval - the golden set is fixed and the corpus is fixed, so
there is no sampling to be noisy about. It is slack for legitimate corpus edits: adding a
document dilutes the pool slightly, and a gate with no slack would fire on every authoring PR and
be disabled within a week.

**`GATE_RECALL_AT_5` did not move, and that is a deviation from the registered rule.**
`PREREGISTRATION-Q39.md` §3.1 registered recalibration at *the same relative margin* - 14.0% below
the measurement - which would put this at **0.38**. The measurement fell, so the formula lowers the
gate. **A relative-margin rule loosens the gate exactly when quality drops**, which converts a
regression into the new baseline and is the one thing a regression gate exists to prevent. So the
rule applied here is the tighter of the two: the registered formula, or the constant already
standing. For `MRR` the formula tightened (0.18 → 0.26) and was taken; for `recall` it loosens and
0.40 stands, still below the 0.442 measured. Q48 then moved `MRR` to 0.286, where the formula
gives 0.235 and this constant is the tighter one again, so 0.26 stands and its margin narrows.

**This deviation was decided after seeing the data**, which is normally how a rule gets bent to
fit. What makes it defensible is direction: it is strictly more demanding than what was registered
in both cases, so it cannot flatter the change it was chosen alongside. Recorded here rather than
only in the write-up, because the next person to read these constants is reading this file.

**It certifies nothing.** Clearing it means retrieval has not got materially worse than a pipeline
still recorded as below its own floor - 0.442 against a registered 0.60, and 0.286 against 0.45.
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
        f"{GATE_RECALL_AT_5}. Measured at {MEASURED_RECALL_AT_5} on 2026-09-13. This gate notices "
        "change; it does not certify quality."
    )
    assert result.overall.mrr >= GATE_MRR_AT_5, (
        f"MRR@5 {result.overall.mrr:.3f} is below the calibrated gate {GATE_MRR_AT_5}. "
        f"Measured at {MEASURED_MRR_AT_5} on 2026-09-13."
    )


def test_the_gate_is_below_the_measurement_and_the_measurement_is_below_the_floor(
    seeded_store: PgVectorPastIncidentStore,
) -> None:
    """The three levels, asserted as an ordering so nobody quietly inverts them.

    A gate above the measurement fails every build. A gate at the registered *floor* would do the
    same, for as long as the pipeline sits under it - which is still the situation after Q39 and is
    why the floor is a line in a write-up rather than an assertion in CI.

    **Both metrics are asserted now.** Before Q39 only `recall` was, and the omission was not
    noticed until the constants moved: a rule about three levels that checks one of the two numbers
    it governs is a rule with a hole in it.
    """
    assert GATE_RECALL_AT_5 < MEASURED_RECALL_AT_5 < 0.60
    assert GATE_MRR_AT_5 < MEASURED_MRR_AT_5 < 0.45
