# The remaining ten service runbooks, and what changed about how they were written

**Date:** 2026-09-12. **Task:** T6.4. **Subject:** `service-accountingservice`, `-adservice`,
`-currencyservice`, `-emailservice`, `-frauddetectionservice`, `-kafka`, `-paymentservice`,
`-quoteservice`, `-recommendationservice`, `-shippingservice`.

This completes the fifteen service documents the pre-registration registered. Two review rounds
by a reader who did not write them, before the PR.

## The process changed, because the record said to

`ORIGINAL-FIFTEEN.md` recorded that nine blocking findings came out of the Q35 repair and **not
one was in a deletion** — four were in prose written to replace a removed sentence, and the ADR
addendum drew the lesson that replacement prose must be reviewed as new authoring. The obvious
next question is why that prose was wrong, and the answer in every case was that it was written
from memory and then checked, rather than written from a source.

So these ten were written from a **sourced fact sheet compiled first**, by a reader who was not
going to write the documents: a file path, a line number and a verbatim quote for every fact,
plus an explicit in-bounds/out-of-bounds call against ADR-0036 Addendum 1 for each one. Nothing
in the ten was written from recall.

**It worked on the thing it was aimed at.** The first review round checked roughly seventy
distinct numbers and found the large majority exact — the whole kafka memory account, the whole
CPU-retirement account, every log-volume figure, every baseline p95 to three decimals, every edge
kind and error delta. No recall error survived.

**The three blocking findings failed at three different points, and only one of them was the
writing.** The first draft of this paragraph said all three were the same thing — prose widening
a correctly sourced fact — and the reviewer took it apart:

| finding | what the source said | what went wrong |
|---|---|---|
| *"one of only five services with a measured outbound edge"* | ADR-0035 counts five, over the **catalog** | **Widening, between sheet and page.** Restated as a claim about the graph, where it is four; the fifth is the synthetic client whose edge ADR-0017 excludes and which this corpus spent three rounds walling out of service runbooks |
| *"the highest in this world"*, of a container memory reading | the override comment says exactly that | **A sourcing miss.** The source sentence is false on its face and contradicted three times *in its own file*. A sheet recording path, line and verbatim quote reproduces it faithfully and passes it straight through |
| an async edge measurement, with its figures, its duration and the caller's unmoved error ratio | the evidence file, quoted word for word | **A bounds-call miss.** The sheet marked it in-bounds; the corpus had spent rounds two to four requiring `service-checkoutservice` to abstract exactly that to *"a callee's failure was observed not to reach the caller"* |

So the lesson is not that sourcing fixed everything except the sentence-writing. **Sourcing
removes recall errors and leaves two other failure points intact**: a source can be wrong, and a
correctly quoted fact can still be out of bounds. The fact sheet and its in/out calls need
reviewing on the same terms as the prose, and on this batch neither was.

The corpus cannot hold two standards for one measurement, so the third finding resolved the way
it had to: the more exposed passage gave way to the abstraction already agreed elsewhere.

## Edits to already-seeded documents, named because Q36 exists for this

Three documents outside the ten changed, all **body-only** — no heading moved, so these move
`body_sha256` and not `sha256`:

- `service-cartservice.md` and `service-productcatalogservice.md`: the 1.9-9.7ms resting band is
  now labelled as a median p95 over a twelve-hour census rather than quoted bare.
- `world-warm-up-latency.md`: the same band, in the document that states it most broadly.

The reason is a contradiction the new batch surfaced. `service-shippingservice`'s resting mean is
**12.35ms**, measured over the clean 45-minute baseline, and it is one of the eleven services
that band covers. Both figures are right and they are different statistics over different
windows; until now nothing said so, and a reader holding three documents would have seen a
service placed inside a band it sits outside.

This is exactly the case Q36 was closed for: a body-only edit to a seeded document used to be
invisible in the record. It is not any more, and these three are named here so the change is
attributable rather than merely detectable.

## One defect left in place, deliberately

`compose/prometheus/alert-rules.yml` describes cartservice's baseline as *"181 consecutive
samples, min and max alike"*. The manifest has its maximum at **1.9235**, not 1.9000.
`service-cartservice.md` quotes the comment faithfully, so the imprecision is the comment's.

The comment is not cheaply correctable: that file is the first entry in `OBSERVABILITY_FILES` and
the digest is taken over the file, comments included, so editing it moves `observability_digest`
and re-founds comparability for every recorded figure. It is queued as **Q38** rather than
slipped into a runbook review.

What was fixed instead is the runbook side, for free: the three new documents whose readings
*are* exactly equal now say so to four decimal places, so one phrase no longer covers two
different precisions.

## What this does not settle

- **Whether the fact sheet is right. Nobody reviewed it.** The reviewer checked the *runbooks*
  against the tree, which catches a sheet error only where it reached the page. A fact the sheet
  got wrong that was silently overridden while writing, a bounds call that was ignored, or a fact
  the sheet never collected, would all be invisible to that check — and the batch has one
  confirmed sourcing miss and one confirmed bounds-call miss that reached the page, so the sheet
  is known to be imperfect rather than merely unverified. The next batch written this way should
  have the sheet read as well as the prose.
- **Whether the fourth optimistic write-up in a row is the last one.** The first draft of this
  file said all three blocking findings were the same failure and that the sheet had been
  spot-checked. Both were flattering and both were wrong, in the section whose job is to say what
  is not established. `ORIGINAL-FIFTEEN.md` records three earlier instances of the same lean.
  Four in a row is a pattern rather than four accidents, and nothing in this process catches it
  except a reader who did not write the document.
- **Whether `service-kafka` is too long.** It is the longest document in the corpus by some way,
  because kafka carries the most-corrected finding in the repository and three superseded
  diagnoses worth recording. Retrieval is measured over sections, so length costs less here than
  it would in a flat corpus, but nothing has measured that.
- **Whether the fifteen are useful.** That is the recall measurement, and it has not been taken.
