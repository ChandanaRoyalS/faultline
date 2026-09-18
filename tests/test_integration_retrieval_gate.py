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

**And it reads both `k`** (ADR-0040). It read `k = 5` alone until 2026-09-14, because that is what
the floor is stated in - while `ContextSettings.retrieval_k` is **3**, so a regression at the only
depth production uses could clear this gate untouched. Q48 established the two are not nested.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

from evalharness.retrieval import PREDATES_T6_4, load_golden, measure
from faultline.context.acceptance import ledger_path, ledger_store
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

MEASURED_RECALL_AT_3 = 0.395
MEASURED_MRR_AT_3 = 0.233
"""The same measurement read at `k = 3`, which is the depth production retrieves at.

Unchanged by Q48's reconciliation: removing the two orphan chunks moved `MRR@5` and left every
`k = 3` figure byte-identical. Not a coincidence worth relying on - see ADR-0040 clause 3 - but
recorded because it is the reason these two numbers have one date and the `k = 5` pair has two.
"""

GATE_RECALL_AT_3 = 0.35
GATE_MRR_AT_3 = 0.21
"""**Calibrated at the same relative margins as the `k = 5` pair** - 11.4% and 9.9% below, from
rounding the 9.5%/9.1% formula down to two places. Derived rather than chosen, so that the two
depths cannot drift into being governed by different degrees of slack.

**No floor accompanies these** (ADR-0040 clause 4). A floor says what good would look like and is
worth having only if it was argued before the answer was known. `recall@3` was measured at 0.395
before anyone proposed a `k = 3` floor, so any number written now would be chosen with the answer
in hand. These are regression gates; they certify nothing.
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
            # The committed ledger, not an empty one: this fixture refused all ten postmortems
            # on every main commit from 2026-09-15 to 2026-09-18 - twenty-five red runs - while
            # the image job beside it kept publishing (`acceptance.LEDGER_FILE`).
            seed(store, DEV_ROOT, ledger_store(ledger_path(DEV_ROOT)))
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


def test_retrieval_has_not_regressed_at_the_depth_production_retrieves(
    seeded_store: PgVectorPastIncidentStore,
) -> None:
    """**ADR-0040 clause 1.** The gate read `k = 5` only, and production retrieves `k = 3`.

    `ContextSettings.retrieval_k` is 3 and T6.4 set it there *because nothing read the old 5*. So
    for the whole life of this gate, a regression at the only depth the pipeline actually uses
    could pass it - and Q48 showed the two are not nested: each arm applies its own `LIMIT k` and
    `fuse` takes `limit=k`, so `k = 3` and `k = 5` are different retrievals, not one read twice.

    Additive on purpose. Nothing that passed before can fail because a condition was added, which
    is what makes this safe to land in the same breath as an ADR about which `k` decides - the
    clause that could be self-serving is clause 2, and it governs the *next* measurement rather
    than this file.
    """
    result = measure(seeded_store, load_golden(), k=3, predates_task=PREDATES_T6_4)

    assert result.overall.recall_at_k >= GATE_RECALL_AT_3, (
        f"recall@3 {result.overall.recall_at_k:.3f} is below the calibrated gate "
        f"{GATE_RECALL_AT_3}. Measured at {MEASURED_RECALL_AT_3} on 2026-09-14, on the reconciled "
        "corpus. This is the depth production retrieves at."
    )
    assert result.overall.mrr >= GATE_MRR_AT_3, (
        f"MRR@3 {result.overall.mrr:.3f} is below the calibrated gate {GATE_MRR_AT_3}. "
        f"Measured at {MEASURED_MRR_AT_3} on 2026-09-14."
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

    # **Two levels at `k = 3`, not three** - ADR-0040 clause 4 sets no floor there, because
    # `recall@3` was measured before anyone proposed one. The ordering that remains is still
    # worth asserting: a gate above its own measurement fails every build at either depth.
    assert GATE_RECALL_AT_3 < MEASURED_RECALL_AT_3
    assert GATE_MRR_AT_3 < MEASURED_MRR_AT_3
