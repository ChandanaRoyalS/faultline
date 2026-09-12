# The original fifteen runbooks, read against ADR-0036 Addendum 1

**Date:** 2026-09-12. **Task:** T6.4, Q35. **Subject:** the pre-T6.4 corpus, seeded and scored.
**Verdict:** six fail materially, a seventh in one section, three on framing, five untouched.

## Why this sweep happened at all

Addendum 1 sharpened ADR-0036's rule after five newly authored documents were removed. It was
written to govern documents not yet written, and nobody read the fifteen that already existed
against it. The prompt to do so came from noticing one sentence in `alert-high-latency.md` while
editing it for an unrelated reason. **One sentence was the visible part of six documents.**

The sweep was run by a reader who did not author the fifteen, against every scenario in
`evals/scenarios/` including comments, `ground_truth`, `expected_evidence` and every
`discriminator` entry.

## What makes this heavier than the batch Addendum 1 was written about

**They are seeded and they have been reaching scored runs.** 167 of 537 run manifests carry
`freeze.corpus.documents` including all fifteen `runbook:*` ids at one corpus hash. The removed
batch's write-up could say *no measurement is affected*; that sentence is not available here.
The 167 runs are not invalid, and they are not measurements of an uncontaminated pipeline
either.

**And a repair would have been invisible.** `corpus_state()` hashed `document_id|section` and
never a chunk body, so editing a runbook under an existing heading changes what every scored run
reads while leaving the corpus key byte-identical. That was opened as Q36 and closed before this
repair, deliberately and in that order — otherwise the contaminated runs and the repaired ones
share one key, which is the failure ADR-0014 exists to prevent.

## The six, ranked by how much a scored run was helped by reading them

**Every repair below removes a sentence, and every one of the ten edited documents also gained
new factual claims** — nine of them under a new or renamed `##` heading. Across the eleven
runbook files touched (the ten, plus one cross-reference in `service-redis-cart`, which is not one
of the fifteen) the change is **150 insertions against 107 deletions**.

That new prose is unreviewed material of exactly the kind this file is about, so it went through
three review rounds of its own. **Nine blocking findings, and where they fell is the useful part:**

| where the defect was | count |
|---|---|
| prose written to replace a removed sentence | **4** |
| these write-ups | **3** |
| the removal side | **1** |
| text the repair never touched | **1** |

The four in replacement prose were mine and were written from memory: a mechanism property that
is actually a property of the target, an ADR cited for a sentence it does not contain, a
self-correction for an error the document had never made, and an overstatement of what one ADR
measured. The removal-side one is the three `alert-*` documents left declaring `actions:` front
matter whose justifying prose had just been deleted. The untouched-text one is a sentence this
repair left alone which a later edit elsewhere turned into a contradiction between two runbooks.

**And three of the nine were in this file**, which has been corrected three times in the same
direction — each time making the repair look smaller or cleaner than it was: *"in every case the
removal of a sentence"*, then *"five of the eleven gained a new section"*, then a finding split
that put eight of nine in the replacement prose when the true figure is four. Each correction was
honest about its predecessor and introduced a smaller version of the same bias. That is the
pattern to carry forward, because this file exists so a future reader can decide whether the 167
runs need re-reading, and optimism here is not a style problem.

**No document lost the world fact it exists to carry**, and that claim was checked document by
document rather than asserted.

**This repair moves `sha256`, not only `body_sha256`.** Nine of the ten changed a section
heading. Q36 was still necessary — one of the ten is a body-only edit, and the next repair may be
all of them — but the visibility argument for this particular change is stronger than a
body-hash-only reading would suggest.

### 1. `alert-high-error-rate.md` — a culprit-location algorithm

> *"Rank the affected services by ratio. The one with the highest ratio and the fewest inbound
> edges in the dependency graph is the likelier origin."*

Retrieved on `ServiceHighErrorRate`, the paging signal for most of the catalog. It is also
contradicted three paragraphs later by the same document (*"the service with the highest ratio
is often not the one that broke"*), so it was wrong as well as out of bounds.

The document also carried two frequency priors — *"Most incidents in this world are
change-induced"*, *"Errors at this magnitude come from `bad_deploy` … or `bad_config`"* — both
true only because of how the catalog was built, and the instruction *"rank by topology rather
than by loudness"*, which collides with four scenarios, two of them holdout.

**Kept:** the rule, the zero baseline, what the `service_name` label counts, and the arithmetic
that a ratio's denominator is each service's own traffic. That last one is the mechanical fact
the ranking instruction was a bad gloss on.

### 2. `class-dependency-latency.md` — the method, and the wrong method

> *"The caller's p95 rises; the callee's own p95 does not."*
> *"Traces separate cause from effect faster than metrics here: the span tree shows which hop
> holds the added time, and that hop is the injected boundary."*
> *"A latency alert with no error alert beside it is this class more often than anything else."*

The second sentence is the method, stated as an instruction — the same shape as the sentence
removed from the first `service-cartservice.md`. The third is a class frequency prior.

**And the first is false.** Every measured `dependency_latency` scenario in this catalog has the
shaped service's *own* p95 move. The corpus was handing over a discriminator and the wrong one.

**The replacement was false too, on the first attempt, in the opposite direction.** It said the
shaped service's own p95 rises — full stop — and this world holds the counter-example: a leaf
service was shaped cleanly for a full alert budget and **its p95 never moved and no rule fired**,
because a leaf's delayed egress lands after its server span has closed. That scenario is blocked
on exactly this measurement and its file states the general rule in bold: *a mechanism's
observability is a property of the target, not of the mechanism*. Both the old sentence and my
first replacement stated a per-target behaviour as a per-mechanism one, in opposite directions.
The document now carries the conditional and the counter-example.

**Replaced with** what the mechanism does: the delay is paid per packet crossing the shaped
interface, with what that does to the shaped service's own metrics depending on whether its
handler makes downstream calls; where it moves, it moves by a multiple set by the operation's
round-trip count rather than by a fixed factor; a delayed call still succeeds, so the error ratio
stays at zero; the qdisc attaches at once while the visible onset lags by the rate window and the
`for:` clause; and the ceiling past which the class silently becomes a different one.

**That ceiling is ADR-0013's, not ADR-0007's**, and the first draft cited ADR-0007 because
`evals/scenarios/SPLIT.md` does. ADR-0007 contains no timeout reasoning at all. The runbook now
cites ADR-0013; **SPLIT.md is left as it stands** — it is committed allocation evidence and is not
edited here — and the mis-citation is queued as Q37 instead. The reviewer's dissent is worth
recording: SPLIT.md's own rule forbids editing *to accommodate a scenario*, which a citation fix
is not, and the file has now propagated this error once into a seeded document by way of an author
checking a source. Q37 bounds the exposure by naming it; the asymmetry stays.

**One more defect was created here and then removed.** The first repair of this document kept the
line *"Reverting configuration changes nothing here, because no configuration was changed"* — which
ADR-0027 exists to overturn, and which a later edit to `action-revert-config` turned from a stale
sentence into a live contradiction between two runbooks a proposer can hold at once. Both now
carry ADR-0027's actual position: the qdisc is a thing an operator can delete, it was measured on
one target, and the extension to the other is recorded by that ADR as inference rather than
measurement.

### 3. `alert-no-traffic.md` — "distinguishable only by…"

> *"This looks identical on this rule and is distinguishable only by looking somewhere other than
> the metrics: container state, container logs, and whether neighbouring services still show
> calls to it."*
> *"Checking container liveness first separates the two in one query."*

Addendum 1's banned form almost verbatim, and it reconstructs a dev scenario end to end — that
scenario's own file names its discriminator in those terms.

**Kept, and strengthened:** that the rule reads absence of `calls_total` samples, that
`calls_total` is span-derived so every link in that chain is a way for samples to stop, and that
the rule therefore cannot separate a service that stopped from telemetry that stopped — *not
"usually cannot", cannot*. Stating the limit of the instrument is in bounds. Stating the
procedure for getting around it is not.

### 4. `alert-high-latency.md` — the sentence that started the sweep

> *"Latency without a matching error-rate alert is most often `dependency_latency` … The
> signature is that the caller slows while the callee's own latency stays flat."*

A class frequency prior and the same false discriminator as finding 2.

**Replaced with** what the rule reads: a `service_name`-grouped quantile over `latency_bucket`,
scoped to a service rather than to a call path, with the rate window and `for:` clause that put
the alert's `activeAt` minutes behind the onset.

### 5. `class-bad-deploy.md` — a holdout's reason for being a holdout

> *"The service named by the loudest alert is frequently not the service whose image changed."*

One holdout scenario's file carries the comment *"Why this scenario is in the holdout, stated
plainly"* immediately above the line this paraphrases.

> *"on the service the alert names or one hop upstream of it"*

A traversal instruction keyed to that shape, and directionally wrong: the relationship is the
downstream one, which `Direction.CANDIDATE_CAUSE` documents and which does not compose.

**Kept:** what the change record holds, and the mechanical consequence that a container which is
not running emits no spans, so no series exists for it at all.

### 6. `class-bad-config.md` — a banned phrase-form and a falsified claim

> *"The distinction is whether the image moved or a value moved"* — Addendum 1's banned form, and
> the discriminator of two scenarios, one holdout.
> *"usually produces connection errors in the service's own logs with the address quoted verbatim
> - the fastest confirmation available"*

**Falsified by a recorded correction in another scenario**, whose own file says the authored
version claimed the logs would show the address and *they do not* — that capture's logs are
exculpatory rather than diagnostic. The runbook told a reader to expect the opposite.

**Kept and corrected:** the change record holds the variable and both values; what the logs hold
is not uniform, and the document now says so and says it was wrong before.

### 7. `world-uninstrumented-services.md` — one section

> *"an incident whose alerts all name instrumented services may still originate in one that
> cannot alert"*

Collides with a holdout scenario and a dev one. Section removed.

**A count was also wrong in the other direction.** It said two of the three alert rules cannot
evaluate for `featureflagservice`. The scenario file it draws on is explicit that *neither
`calls_total` nor `latency_bucket` has any series for it under any spelling* — so all three
cannot. The two-of-three figure was the count for the `calls_total` rules alone.

## The three framing cases, and the ADR's own share of the blame

`class-resource-exhaustion`, `action-revert-config` and `action-scale-unavailable` each stated a
true mapping as a **census of the catalog**: *"every `resource_exhaustion` scenario carries
`expected_remediation_class: config_revert`"*, *"the most-proposed entry in the catalog"*,
*"There is no `scale` scenario in the catalog"*.

**The sweep first listed four, and `action-restart-service` was grouped wrongly.** It carries no
census sentence — it says *"That is the whole mechanism"*, which is the framing the other three
were moved to — and it was left untouched. The error is recorded rather than quietly dropped,
because a sweep that mis-groups a document is a sweep whose other groupings are worth re-reading:
the remaining three were re-checked against their own text and each does carry the quoted
sentence.

ADR-0036's body commissioned those sentences and Addendum 1 banned their framing, and both halves
were live at once. ADR-0036 Addendum 2 decides it: the fact is in bounds, the census is not, and
the in-world framing was already sitting beside it in the same documents. Reframed rather than
deleted.

`class-resource-exhaustion` carried one further problem, removed: *"the class is confirmed from
logs rather than from which alert fired"* is wrong advice for a scenario whose whole trap is that
its container evidence matches this class and its cause is a different one.

## The five left untouched, named because they are the model

`action-rollback-image`, `action-restart-service`, `world-saturation-is-invisible`,
`world-tracing-artifact-edges` and `world-warm-up-latency` as edited earlier the same day. Each
states a property of the world or of the instrument, and **none tells a reader what a shape of
evidence means.** `world-saturation-is-invisible` is the sharpest example: it states that a
negative cannot be concluded, which is the opposite of a discriminator.

`action-restart-service` is here rather than among the framing cases because it never carried a
census sentence — it says *"That is the whole mechanism"*, which is the framing the other three
were moved to.

`world-warm-up-latency` is the useful precedent. It was one phrase away from a prior — *"warm-up
is the most common explanation for it"* — and removing that phrase was the entire fix.

## What this does not settle

- **Whether the 167 recorded runs should be re-read.** They are not invalid and they are not
  clean. Nothing in their manifests distinguishes them from a run on the repaired corpus, and
  after Q36 nothing needs to: a run recorded after this carries `body_sha256` and they do not.
- **Whether any recorded score moved because of these sentences.** Unmeasurable without re-running
  them, which is not funded. The honest statement is that the corpus carried answer-key material
  and the effect size is unknown.
- **Whether a second sweep would find more.** The sweep was one pass by one reader; the repair
  then went through two further review rounds, which returned nine blocking findings, so the
  reading is not thin. But every round has returned something, and the last one returned four.
  A round that returns nothing has not happened yet.
- **Whether `class-dependency-latency`'s `actions:` list should now name `revert_config`.**
  `roles.py` surfaces action runbooks to the proposer *only* from the class runbook's own list, so
  a `dependency_latency` verdict never sees `action-revert-config` — even though ADR-0027 makes
  that a scorer-accepted answer for one scenario in the class. Adding it would change what a
  scored run reads. That is a corpus change to measure, not one to slip in during a repair. Left
  alone deliberately, and recorded rather than silently decided.
