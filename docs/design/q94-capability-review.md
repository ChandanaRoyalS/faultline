# Q94 — the narrative review the capability move required

**Date:** 2026-09-24 · **Task:** T7.1 (Q94) · **Reviewer:** Chandana Sorakundla

`CAPABILITY_VERSION` moved from `cap:dd651ccc` to `cap:d2b243e0`. As designed, that failed
`test_every_narrative_was_reviewed_against_the_current_capability_set` on all sixteen bundles.
This document is the review the re-stamp rests on, in the shape
`docs/design/t6.1-capability-review.md` set. The replay over the recorded windows is in
`docs/evidence/q94-trace-tool/`.

## What moved, and what each change could falsify

One capability input moved: `TOOL_BEHAVIOUR_REVISION` **3 → 4**. The tool surface is unchanged:
`trace_query` keeps its name and signature. `CAPTURE_SET` is unchanged. Three behaviour changes
sit behind the one bump, all in `faultline.tools.spantree` and the trace tool's parse.

**1. Rendering depth per world.** v1 keeps 6. v2 renders to 16: the deepest span measured on
the running world was 15, plus one to spare. v1's output is byte for byte what it was.

*The claim shape this could falsify:* a narrative asserting that a call was not visible in the
trace, sat too deep to see, or that the tool elided the span that mattered.

**2. An ERROR span's status message is printed.** OTLP's `status.message` was dropped at parse,
so nothing could print it. On both worlds an error span now carries its service's own reason.

*The claim shape this could falsify:* a narrative asserting that a failing service gave no
reason a responder could read, or that its error carried no attribute or text pointing at the
cause.

**3. Rule 0 of the degrading hop.** When an erroring span gave up on a call that had already
started and ran at least a second past it, the hop names the deepest such call instead of the
timeout.

*The claim shape this could falsify:* a narrative stating which hop the tool named, or that the
tool pointed at a timeout's edge rather than at what was being waited on.

## What the review looked for, and what it found

Every `incident.md` under `evals/scenarios/artifacts/dev/` (13) and `holdout/` (3) was searched
for `trace`, `span`, `hop`, `elided`, `deeper`, `status`, `message`, `attribute`, `reason`,
`says nothing`, `said nothing`, `timeout`, `deadline`, `waiting`, and every hit was read in
context rather than counted.

| Claim shape | Hits | Disposition |
|---|---|---|
| A call not visible / elided / too deep | **1** | `v2-product-catalog-freeze`: *"the trace view elided it, so the tool did not name the service being waited on. The degrading-hop line named the proxy hop."* **Falsified by changes 1 and 3**, which exist because of it. Rewritten against the replay's output: the tool now names frontend's call into the catalog, *still waiting 516.8 s after frontend-proxy/ingress gave up*, and in three of ten frontend traces frontend's call into recommendation. The paragraph on the catalog's own traces is corrected too. The catalog *did* appear in the window, in requests it served after the resume in about a tenth of a second. It never appeared as an error. The Detection-notes line *"waiting on something one level too deep to see"* is corrected with them. `expected_evidence`'s `traces:` item moves with the prose, and the scenario fingerprint does not |
| A failing service gave no readable reason | **1** | `product-catalog-flag-failure`: *"Nothing in the metrics stack could have surfaced it - not a dashboard, not an alert, not a trace attribute"*, and in Root cause *"no amount of investigating product catalog would have found it"*. **Falsified in part by change 2.** The catalog's error status names the enabled failure flag. Its accepted postmortem records frontend receiving it as the gRPC error's details (*"gRPC status 13 with a details string that names the enabled flag"*). On v2, R1 read the span's message as *Product Catalog Fail Feature Flag Enabled*. The T6.1 review read this sentence as *"the flag's value is in no telemetry"*, and that part stands. What no longer stands is that nothing pointed at a flag. Both sentences now say what the error text gives (that a flag made the catalog fail) and what it does not give (where the flag is set, or who set it). v1's own span message was not re-read: v1's traces are gone. The claim rests on the postmortem's evidence and v1's server interceptor, which sets a span's status from its gRPC status |
| Which hop the tool named | **0 besides the freeze** | No v1 narrative quotes a degrading hop. The trace passages in `cart-bad-image-tag` and `cart-redis-misconfig` (*"Checkout spans failing on their call to cart"*), `payment-telemetry-blackout` (checkout's client spans to payment keep succeeding) and `email-wrong-image` are statements about the world. None is a hang under a timeout, and none is a claim about the tool's line |
| "Says nothing" / "no reason" | **3** | `cart-bad-image-tag`: loadgenerator's error *rate* *"says nothing about cause"*, a metric, unaffected. `recommendation-memory-squeeze`: *"the absence of a crash message"*, a log claim, unaffected. `email-wrong-image`: a process *"with no reason was stopped by something else"*, about kills, not trace text, unaffected |
| Per-hop arithmetic, "one hop away" | **5** | `cart-dependency-latency`, `productcatalog-dependency-latency`, `shipping-quote-misconfig`, `shipping-wrong-image`, `email-wrong-image`: the fault's geometry, unchanged by any tool |

**Fourteen narratives needed no change** and are re-stamped only: `ad-memory-squeeze`,
`cart-bad-image-tag`, `cart-dependency-latency`, `cart-redis-misconfig`,
`currency-cpu-throttle`, `flag-service-crashloop`, `frauddetection-memory-squeeze`,
`payment-telemetry-blackout`, `redis-cart-dependency-latency`, `shipping-quote-misconfig`,
`shipping-wrong-image` (dev), and `email-wrong-image`, `productcatalog-dependency-latency`,
`recommendation-memory-squeeze` (holdout). **Two were rewritten where the change falsified
them**: `v2-product-catalog-freeze` and `product-catalog-flag-failure`.

## The conclusion, stated as a limit rather than as a pass

The stamps move to `cap:d2b243e0` on the basis above. **What this review did not do**, as at
T6.1: it did not re-verify each narrative's findings against its captures. It asked three
questions derived from three changes and answered them. A claim falsified by something else
would not have been caught here.

**Two consequences outside the narratives.**

- `product-catalog-flag-failure` is a v1 dev narrative, so the retrieval corpus's text moves.
  `generations.CURRENT_CORPUS_SHAPE` is compared against the *ingested* corpus (Q61), so it
  moves at the next seed, together with the class runbooks Q92 already queued. The deployed
  corpus will disagree with the tree until then, and the corpus-drift check will report that
  rather than hide it.
- Every figure at `cap:dd651ccc` stays a figure at `cap:dd651ccc`. A trace-dependent verdict
  after this move is a different measurement, and figures are not pooled across the two stamps.
