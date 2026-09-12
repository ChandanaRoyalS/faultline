"""Retrieval quality: a golden set, `recall@k` and MRR (T6.4).

`PREREGISTRATION-T6.4.md` §2.2 and §2.3. This repository has had hybrid retrieval since T2.4b
and has never measured whether it finds the right thing: `recall@`, `MRR` and `golden set` all
returned zero hits across `src/`, `tests/`, `evals/` and `scripts/` when that document was
written.

**No model runs here.** Embeddings are local, recall and MRR are arithmetic, and a model call in
this module is a defect.

Three decisions are made in this file rather than in the write-up, because they decide what the
number means:

**1. Retrieval returns chunks; the golden set labels documents.** A query's result is the top `k`
*chunks* - what the model actually reads - mapped to their document ids and deduplicated in rank
order. So `recall@5` asks *did a relevant document appear among the documents the top five chunks
came from*, and a query whose five chunks all come from one document is measured over one
document. Asking the store for more chunks until five distinct documents appeared would measure
something the pipeline does not do.

**2. A query with no relevant document is kept and is not scored.** §2.2 requires them: some real
queries should return nothing useful, and a golden set that quietly drops them measures a corpus
that always has an answer. Recall over an empty relevant set is 0/0, so they are excluded from
both means and reported as their own count - with what they returned, so a reader can see whether
the corpus answers anyway.

**3. The split is per label, not per query.** §2.3 registers three numbers - the whole set, the
documents that predate this task, and the documents written for it - so that *documents by the
measurement's author are easier to find* shows up as a gap rather than as a caveat. Partitioning
*queries* by where their answer lives turned out to be degenerate on the harvested set: **no
query has an answer lying entirely among the fifteen older runbooks**, because the questions the
pipeline actually asks are about things only the newer documents cover. So the partition is
applied to the labels instead. A query with both an old and a new relevant document contributes
to both rows, each asking only whether *that* half was found. The comparison §2.3 wanted is
preserved; the per-query version of it is not available on this data, and that is itself a
finding about the corpus.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

GOLDEN_SET = Path("evals/retrieval/golden.yaml")

PLANNER = "planner"
SYNTHESIZER = "synthesizer"


class Searcher(Protocol):
    """The half of `PastIncidentStore` this module uses."""

    def search(self, query: str, k: int = 5, exclude_origin: str | None = None) -> Any: ...


@dataclass(frozen=True, slots=True)
class Label:
    """One hand-labelled relevant document, with the reason it is relevant.

    The reason is required rather than optional. A label with no stated reason is a label nobody
    can dispute, and the residual weakness §5 names is that the labels and the documents have the
    same author.
    """

    document_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class GoldenQuery:
    """A harvested query, its provenance, and its labels.

    `query` is the text the pipeline actually sent, not a rewrite of it. `source_trajectory` and
    `seq` are what makes that checkable against `trajectory_retrievals` afterwards.
    """

    id: str
    query: str
    role: str
    source_trajectory: str
    seq: int
    harvested_from: str = "none"
    """The `exclude_origin` the run carried, i.e. which scenario this query was sent during.

    Carried so the holdout guard below has something to check. `none` is the product case: a live
    incident has no origin to exclude.
    """

    relevant: tuple[Label, ...] = ()
    note: str = ""

    @property
    def relevant_ids(self) -> frozenset[str]:
        return frozenset(label.document_id for label in self.relevant)

    @property
    def has_answer(self) -> bool:
        return bool(self.relevant)


@dataclass(frozen=True, slots=True)
class QueryResult:
    """What one query returned, reduced to documents in rank order."""

    query_id: str
    documents: tuple[str, ...]
    relevant: frozenset[str]

    @property
    def scored(self) -> bool:
        return bool(self.relevant)

    def recall_at(self, k: int) -> float:
        """**Hit-rate form**: did any relevant document appear in the top `k`.

        Not |retrieved ∩ relevant| / |relevant|. Most queries here have one relevant document, so
        the two agree on them and diverge only where a query has several - and for a corpus this
        small the question being asked is *did it find the thing*, not *did it find all of them*.
        Stated here because the two are both called recall and are not the same number.
        """
        return 1.0 if self.relevant & set(self.documents[:k]) else 0.0

    @property
    def reciprocal_rank(self) -> float:
        for position, document in enumerate(self.documents, start=1):
            if document in self.relevant:
                return 1.0 / position
        return 0.0


@dataclass(frozen=True, slots=True)
class Report:
    """One row of the measurement. `queries` counts only the scored ones."""

    label: str
    k: int
    queries: int
    recall_at_k: float
    mrr: float

    def line(self) -> str:
        return (
            f"{self.label:<28} n={self.queries:<4} "
            f"recall@{self.k}={self.recall_at_k:.3f}  MRR={self.mrr:.3f}"
        )


@dataclass(frozen=True, slots=True)
class Measurement:
    """Every number this task registered, in one object."""

    overall: Report
    by_corpus_age: tuple[Report, ...]
    by_role: tuple[Report, ...]
    unanswerable: tuple[QueryResult, ...] = ()
    results: tuple[QueryResult, ...] = field(default=())

    @property
    def mean_documents_returned(self) -> float:
        """**How many distinct documents the top `k` chunks actually spanned.**

        The cut is applied to chunks (decision 1), so this is the ceiling on what any
        document-level recall can see. A value near 1 means the measurement is mostly asking
        *did the single best-matching document happen to be right*, which is a much harder
        question than `recall@k` sounds, and the number cannot be read without it.
        """
        if not self.results:
            return 0.0
        return sum(len(r.documents) for r in self.results) / len(self.results)

    def render(self) -> str:
        lines = [self.overall.line(), ""]
        lines += [r.line() for r in self.by_corpus_age]
        lines += [""] + [r.line() for r in self.by_role]
        if self.unanswerable:
            lines += [
                "",
                f"{len(self.unanswerable)} query(ies) labelled as having no relevant document, "
                "excluded from both means.",
            ]
            for result in self.unanswerable:
                returned = ", ".join(result.documents[:3]) or "nothing"
                lines.append(f"  {result.query_id}: returned {returned}")
        lines += [
            "",
            f"mean distinct documents in the top {self.overall.k} chunks: "
            f"{self.mean_documents_returned:.2f}",
        ]
        return "\n".join(lines)


PREDATES_T6_4: frozenset[str] = frozenset(
    {
        "runbook:alert-high-error-rate",
        "runbook:alert-high-latency",
        "runbook:alert-no-traffic",
        "runbook:class-bad-config",
        "runbook:class-bad-deploy",
        "runbook:class-dependency-latency",
        "runbook:class-resource-exhaustion",
        "runbook:action-restart-service",
        "runbook:action-revert-config",
        "runbook:action-rollback-image",
        "runbook:action-scale-unavailable",
        "runbook:world-saturation-is-invisible",
        "runbook:world-tracing-artifact-edges",
        "runbook:world-uninstrumented-services",
        "runbook:world-warm-up-latency",
    }
)
"""The fifteen runbooks that existed before T6.4 authored a document.

**Written out rather than derived**, and that is §2.3's requirement: the comparison is *are the
documents written by the measurement's author easier to find*, and a set derived from the corpus
would move every time a document is added, so the comparison would stop being the same
comparison. The ten dev narratives are not listed because no query in the golden set has one as
an answer; a narrative answering a query would need adding here and saying so.

Note that six of these fifteen were repaired at Q35 and three more were edited. They predate the
task in authorship, which is what the split is about, not in wording.
"""


def load_golden(path: Path = GOLDEN_SET) -> tuple[GoldenQuery, ...]:
    """Load and **refuse a holdout-derived query**.

    A golden set is not a retrieval corpus, so nothing that guards the corpus looks at it - and a
    synthesizer query carries four specialist findings in its text. Committing one harvested from
    a holdout run would put that run's findings into a file in this repository, permanently,
    where anyone authoring against the golden set would read them. That is ADR-0008 axis 1
    arriving through a channel no existing guard checks, and it is checked here rather than
    trusted to whoever next runs the harvest.
    """
    from evalharness.freeze import holdout_origins

    payload: Any = yaml.safe_load(path.read_text())
    queries = tuple(_query_from(entry) for entry in payload["queries"])

    held = set(holdout_origins())
    offenders = sorted(q.id for q in queries if q.harvested_from in held)
    if offenders:
        raise ValueError(
            f"{offenders} were harvested from a holdout run. A holdout scenario's findings travel "
            "in the query text, and a committed golden set is a permanent, unquarantined copy of "
            "them (ADR-0008 axis 1)."
        )
    return queries


def _query_from(entry: dict[str, Any]) -> GoldenQuery:
    return GoldenQuery(
        id=str(entry["id"]),
        query=str(entry["query"]),
        role=str(entry["role"]),
        source_trajectory=str(entry["source_trajectory"]),
        seq=int(entry["seq"]),
        harvested_from=str(entry.get("harvested_from", "none")),
        relevant=tuple(
            Label(document_id=str(item["document_id"]), reason=str(item["reason"]))
            for item in entry.get("relevant", ())
        ),
        note=str(entry.get("note", "")),
    )


def documents_of(hits: Iterable[Any]) -> tuple[str, ...]:
    """Chunk hits to document ids, deduplicated in rank order.

    Decision 1 in this module's docstring. `dict.fromkeys` because insertion order is the rank
    order and a `set` would discard it.
    """
    return tuple(dict.fromkeys(hit.chunk.document_id for hit in hits))


def run_query(store: Searcher, query: GoldenQuery, k: int) -> QueryResult:
    hits = store.search(query.query, k=k)
    return QueryResult(
        query_id=query.id,
        documents=documents_of(hits),
        relevant=query.relevant_ids,
    )


def _report(label: str, k: int, results: Sequence[QueryResult]) -> Report:
    scored = [r for r in results if r.scored]
    if not scored:
        return Report(label=label, k=k, queries=0, recall_at_k=0.0, mrr=0.0)
    return Report(
        label=label,
        k=k,
        queries=len(scored),
        recall_at_k=sum(r.recall_at(k) for r in scored) / len(scored),
        mrr=sum(r.reciprocal_rank for r in scored) / len(scored),
    )


def measure(
    store: Searcher,
    golden: Sequence[GoldenQuery],
    k: int,
    predates_task: frozenset[str],
) -> Measurement:
    """Score the golden set and split it three ways.

    `predates_task` is the set of document ids that existed before T6.4 authored any. It is
    passed in rather than derived, because deriving it from the corpus would make the split move
    every time a document is added and the comparison §2.3 asks for would stop being the same
    comparison.
    """
    by_id = {q.id: q for q in golden}
    results = tuple(run_query(store, q, k) for q in golden)
    scored = [r for r in results if r.scored]

    def restricted(result: QueryResult, keep: frozenset[str]) -> QueryResult:
        """The same result scored against only half of its labels."""
        return QueryResult(result.query_id, result.documents, result.relevant & keep)

    old = [
        restricted(r, predates_task)
        for r in scored
        if by_id[r.query_id].relevant_ids & predates_task
    ]
    new = [
        restricted(r, frozenset(by_id[r.query_id].relevant_ids - predates_task))
        for r in scored
        if by_id[r.query_id].relevant_ids - predates_task
    ]

    return Measurement(
        overall=_report("all documents", k, scored),
        by_corpus_age=(
            _report("answer predates T6.4", k, old),
            _report("answer written for T6.4", k, new),
        ),
        by_role=(
            _report(
                f"role: {PLANNER}",
                k,
                [r for r in scored if by_id[r.query_id].role == PLANNER],
            ),
            _report(
                f"role: {SYNTHESIZER}",
                k,
                [r for r in scored if by_id[r.query_id].role == SYNTHESIZER],
            ),
        ),
        unanswerable=tuple(r for r in results if not r.scored),
        results=results,
    )


HARVEST_SQL = """
SELECT r.trajectory_id, r.seq, r.query, r.k, r.exclude_origin, s.role, t.incident_id
FROM trajectory_retrievals r
JOIN trajectory_steps s ON s.trajectory_id = r.trajectory_id AND s.seq = r.seq
JOIN trajectories t ON t.id = r.trajectory_id
ORDER BY r.trajectory_id, r.seq
"""
"""Every retrieval this pipeline has ever performed, with the role that sent it.

The join to `trajectory_steps` is what supplies the role: a retrieval row knows its query and
its results and not who asked. `investigation.py` is explicit that the planner's query and the
synthesizer's are different shapes and that collapsing them would degrade both, so a golden set
that could not tell them apart would be measuring an average of two things.
"""


def harvest(dsn: str) -> list[dict[str, Any]]:
    """Read every recorded retrieval. **No deduplication and no filtering.**

    Both belong to whoever labels the set, in the open, rather than to a query nobody reads
    afterwards. §2.2's whole argument for harvesting is that the query side is not chosen by the
    person who writes the documents, and a harvest that silently dropped rows would be a choice.
    """
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(HARVEST_SQL)
        rows = cur.fetchall()
    return [
        {
            "source_trajectory": row[0],
            "seq": row[1],
            "query": row[2],
            "k": row[3],
            "exclude_origin": row[4],
            "role": row[5],
            "incident_id": row[6],
        }
        for row in rows
    ]


def run_cli(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="faultline-retrieval")
    sub = parser.add_subparsers(dest="command", required=True)

    harvest_cmd = sub.add_parser("harvest", help="dump every recorded retrieval query as JSON")
    harvest_cmd.add_argument(
        "--dsn",
        default=None,
        help="defaults to ContextSettings().postgres_dsn, like every other harness command",
    )
    harvest_cmd.add_argument("--out", type=Path, default=None)

    score_cmd = sub.add_parser("score", help="score the golden set for recall@k and MRR")
    score_cmd.add_argument("--dsn", default=None)
    score_cmd.add_argument(
        "--k",
        type=int,
        action="append",
        default=None,
        help="repeatable. **Both of this task's k values matter and they are different numbers.** "
        "3 is production's: `Investigation.__init__` and `faultline-investigate` both default to "
        "it. 5 is what the registered floor was written against - the pre-registration says "
        "`recall@5 >= 0.60` and, two sections later, that `retrieval_k` stays 3 for the first "
        "measurement, which are not the same pipeline. Default: both, so neither can be quoted "
        "without the other",
    )
    score_cmd.add_argument("--golden", type=Path, default=GOLDEN_SET)
    score_cmd.add_argument("--json", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.command == "harvest":
        from faultline.context.settings import ContextSettings

        rows = harvest(args.dsn or ContextSettings().postgres_dsn)
        dump = json.dumps(rows, indent=2, default=str)
        if args.out:
            args.out.write_text(dump + "\n")
            print(f"{len(rows)} retrieval(s) -> {args.out}")
        else:
            print(dump)
        return 0

    if args.command == "score":
        import psycopg

        from faultline.context.embedding import SentenceTransformerEmbedder
        from faultline.context.settings import ContextSettings
        from faultline.context.store import PgVectorPastIncidentStore

        dsn = args.dsn or ContextSettings().postgres_dsn
        golden = load_golden(args.golden)
        ks = sorted(set(args.k or [3, 5]))
        rounds: list[dict[str, Any]] = []
        with psycopg.connect(dsn) as conn:
            store = PgVectorPastIncidentStore(conn, SentenceTransformerEmbedder())
            for k in ks:
                result = measure(store, golden, k=k, predates_task=PREDATES_T6_4)
                print(f"===== k={k} =====")
                print(result.render())
                print()
                rounds.append(
                    {
                        "k": k,
                        "overall": asdict(result.overall),
                        "by_corpus_age": [asdict(r) for r in result.by_corpus_age],
                        "by_role": [asdict(r) for r in result.by_role],
                        "mean_documents_returned": result.mean_documents_returned,
                        "per_query": [
                            {
                                "id": r.query_id,
                                "documents": list(r.documents),
                                "relevant": sorted(r.relevant),
                                "recall": r.recall_at(k),
                                "reciprocal_rank": r.reciprocal_rank,
                            }
                            for r in result.results
                        ],
                    }
                )
        if args.json:
            args.json.write_text(json.dumps(rounds, indent=2) + "\n")
            print(f"per-query detail -> {args.json}")
        return 0
    return 1
