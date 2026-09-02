# ADR-0034 — the evidence archive

**Status:** accepted, 2026-09-01
**Task:** T2.3, the last of its four deliverables

## Context

T2.3 asks for *"raw evidence payloads and rendered reports archived to S3-compatible object
storage so citations stay re-verifiable forever"*, and the proposal's architecture lists
`S3-compatible (report archive)` beside Postgres and pgvector.

**The function it names is already met, by a different mechanism.** `ToolCallRecord` stores
each envelope inline under its `result_id` with a sha256, and `narrative.py` refuses a
citation it cannot resolve rather than rendering a blank. Citations are re-verifiable today.

This ADR nearly stopped there, and that would have repeated a mistake made hours earlier:
ADR-0016 Addendum 1 declared `budget-exhausted` superseded because a nearby mechanism looked
close enough, and Addendum 2 had to withdraw it. So the question was asked more carefully —
what does the plan's mechanism give that the current one does not?

**Durability independent of the database.** Postgres holds the only copy. A database that is
reset, restored to an earlier point, or pruned does not corrupt the record; it removes the
evidence beneath every citation ever made, and every report that cites it becomes
*unfalsifiable* rather than wrong. "Re-verifiable forever" is a durability claim, and one
copy in one system is not one.

## Decision

MinIO in the platform compose profile, an `Archive` protocol with an S3 implementation, and
envelopes written under `envelopes/{result_id}` — the same handle a citation resolves, so the
archive can answer the only question anyone asks of it.

**The write happens after the commit, and never fails a run.** The trajectory row is the
record; the archive is the copy that outlives it. Losing a finished investigation because
object storage was unreachable would spend the thing being protected on the protection. A
failure logs a warning naming the trajectory and continues.

**Unreachable and unconfigured are different, and only one is silent.** `connect_or_none()`
returns `None` quietly when the archive is switched off, and loudly when it is switched on and
cannot be reached. A system that believes it is archiving and is not would be the exact defect
this project's audits keep finding.

**It is off by default.** On means every agent run reaches for object storage at startup, so a
developer who has not brought up the platform profile pays a connection timeout per run for a
copy they do not need. Nothing is lost by the default that the system had yesterday — the
inline copies are unchanged. `FAULTLINE_ARCHIVE_ENABLED=true` turns it on, and a deployment
should. That is a sentence in a docstring until T5.5 makes it a deployment.

**No digest moves.** `compose_digest` covers three files, all of them the *world's*
(`world/docker-compose.yml` and the two `compose/` world overrides); the platform
`docker-compose.yml` this edits is not among them, and the file says so in its own comments.
`observability_digest` covers the Prometheus, Grafana and Loki configuration. Adding MinIO
invalidates no recorded bundle — the same reasoning ADR-0030 applied to the dashboard.

## Consequences

`boto3` is an optional dependency (`faultline[archive]`), imported lazily inside
`S3Archive.connect`, matching how ADR-0018 treats the embedding model and ADR-0020 the model
client. `make check` never loads it.

Four integration tests run against a real MinIO container: the bucket created on first
connect, an envelope round-tripped unchanged, the archived bytes verified against the same
sha256 Postgres records, and a missing key reading as `None` rather than raising.

**Reports are not archived yet, and this is the honest half of the deliverable.** The plan
says *"raw evidence payloads **and rendered reports**"*. Envelopes are written; the rendered
narrative is not. `report_key()` exists and has no caller — a defined key scheme and an unused
seam, recorded here rather than left for an audit to discover, which is what happened to T2.5
and T2.7. It is a small piece of work and it belongs with whichever task owns the report
surface; naming it here is the point.
