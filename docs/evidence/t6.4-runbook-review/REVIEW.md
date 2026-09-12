# The first five service runbooks failed their ADR-0036 review, after merge

**Date:** 2026-09-12. **Task:** T6.4. **Subject:** PR #269, commit `d5e872f`.
**Verdict:** do not merge — reached after the merge. All five documents are removed.

## What happened, in order

`PREREGISTRATION-T6.4.md` §2.1 registered that the 25 new documents would be authored rather
than generated, and gave ADR-0036's reason: **runbooks sit outside the exclusion filter, so
anything written in one reaches every scored run forever through the one channel the quarantine
does not check.** It also registered that *"the ADR-0036 review is explicit per document rather
than trusted to the substring test"*.

The first five landed with that review **not done**. The mechanical guards passed — all nine of
them, including the new any-spelling scenario-name check added in the same PR — and passing
guards was allowed to stand in for the review the pre-registration had named as the real
control. The review was run afterwards, by a reader who had not written the documents. It
failed.

Nothing was seeded and no scored run has happened since the merge, so `corpus_state()` has not
moved and **no measurement is affected.** The contamination existed in git and nowhere else.
That is luck about timing, not a mitigation of the process failure.

## The two findings that decided it

**1. `service-productcatalogservice.md` carried a holdout scenario's method and its answer.**

`evals/scenarios/productcatalog-dependency-latency.yaml` is `split: holdout`. Its trap is
recorded in the file as *"the loudest signal is on a caller, and there are several callers. The
investigation has to converge on what they share, not rank what they show"*, and its evidence as
*"the set of slowed services is exactly the set that calls product catalog … which localises the
fault by intersection rather than by magnitude"*.

The runbook said:

> an incident naming frontend, checkoutservice and recommendationservice together is the
> signature of something they share rather than of three independent problems. Productcatalog is
> the most common thing they share.

That is the intersection method and the service it converges on, in a document that is never
excluded, for a scenario that is held out.

**2. `service-cartservice.md` and `service-redis-cart.md` jointly carried the discriminator that
separates two dev scenarios.**

`cart-dependency-latency` and `redis-cart-dependency-latency` produce the same four alerts by
delaying opposite ends of the same path. What separates them is whether cartservice's added time
sits in its own handler or inside the Redis client leaf span; `redis-cart-dependency-latency`
records exactly that as the live-only evidence class.

`service-cartservice.md` said *"Look at the client span's self-time against the span's total … a
cartservice handler waiting on a datastore has a leaf span holding the time and almost no
self-time above it."* `service-redis-cart.md` said *"does the cartservice span tree show its own
handler slow, or a Redis client leaf holding the time? The second points here."*

ADR-0036 §"The rule covers dev scenarios too" is explicit that the dev/holdout line is the wrong
place to draw this, and the reason it gives is the one this pair demonstrates: a runbook written
around a dev scenario is a template for writing one around a holdout scenario.

## Six factual errors in the same five documents

Found by the same review and verified against the sources. They did not decide the outcome; they
are recorded because a batch that failed on contamination also failed on accuracy, and the two
failures have the same cause.

| # | document | claim | source |
|---|---|---|---|
| 3 | `service-checkoutservice.md` | *"Seven outbound"* | the document's own list enumerates eight (4 + 3 + 1) |
| 4 | `service-frontend.md` | *"All five **sync**"*, then lists `checkoutservice (330, unmeasured)` | four are sync; the fifth is `unmeasured` |
| 5 | `service-checkoutservice.md` | `unmeasured` means *"the measurement does not license a directional claim"* | `EdgeKind.UNMEASURED`: the direction is measured and known; what is unknown is whether a callee failure propagates. Traversal **does** cross it |
| 6 | `service-productcatalogservice.md` | cites *"upstream traversal is transitive"* for appearing in a caller's radius | that relationship is the downstream one — one step from seeds only, `candidate_cause`, and it does not compose |
| 7 | `service-cartservice.md` | on a cart latency increase, *"nothing fires anywhere else"* | cart has two sync callers; `redis-cart-dependency-latency` measured four `ServiceHighLatency` alerts |
| 8 | `service-cartservice.md` | *"the only application service whose datastore is a separate container"* | `featureflagservice` / `ffs_postgres`, `knowledge/services.yaml` |

A seventh finding — `service-checkoutservice.md` calling checkoutservice *"one of the least often
at fault"* — is a frequency prior over the catalog, which is a property of the answer key rather
than of the world. It is the same failure as finding 1 in a milder form.

## Why deletion rather than repair

The factual halves of these documents are largely sound and `service-redis-cart.md`'s account of
why no alert rule can ever fire for it is exactly the institutional knowledge ADR-0036 asks for.
Excising the offending sections would have kept that.

It was not done, because **the judgement that would decide which sections to keep is the
judgement that just failed, twice, in the same files.** Deletion is the only correction whose
correctness does not depend on it. The text is in git at `d5e872f` and the sound paragraphs can
be recovered a line at a time when the set is re-authored under the sharpened rule, by a process
that reviews before merging rather than after.

## What changes, so this does not recur

- **ADR-0036 Addendum 1**: a runbook may state what is true of the world; it may not state how
  to tell two possible causes apart. The discrimination step is what the scenarios score.
- The per-document ADR-0036 review happens **before** merge and is performed by a reader who did
  not author the document. Five of five failed a review the author had signed off on.
- The sharpened rule is not mechanically checkable and is not being claimed as such. The nine
  guards in `tests/test_runbooks.py` passed on all five of these documents.
