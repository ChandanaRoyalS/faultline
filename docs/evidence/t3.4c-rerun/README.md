# T3.4c re-run — the third investigation of `shipping-wrong-image`

Injected 02:53:58Z, reverted 03:10:09Z. Trajectory `f7afdb76-47cd-45bf-b4fa-52e4be1a7f9d`.
`investigation.txt` is the run as captured; `narrative.md` is the rendered narrative alone.

**This branch is based on `t3.4b-verdict-grounding`, not on `main`.** T3.4b is unmerged, and the
question this run has to answer — whether the pre-onset language boundary reaches the verdict and
the narrative — is only answerable with T3.4b's two-ended truncation present. So T3.4c's changes
sit on top of it and this run exercises both.

## Baseline before injection, checked explicitly

Still no gate on this path (the T4.1 note in `docs/PLAN.md`). Checked by hand at 02:53:33Z:
**0 active alerts**, no service with p95 over 1000ms, 15 services reporting, no open incidents,
no active injections. One service at 0.000 req/s, `frontend-proxy` — the clean state, not a
fault: the committed baseline `evals/baselines/20260824T033742Z` records it at 181 consecutive
samples of 0.0. **Nothing needed repairing**, and unlike T3.4b no incident state needed clearing.

## The three verdicts

| | **T3.4** `e7739dec` | **T3.4b** `6b9715de` | **T3.4c** `f7afdb76` |
|---|---|---|---|
| fault class | `bad_deploy` ✓ | `unknown` ✗ | **`bad_deploy`** ✓ |
| fix class | `rollback` ✓ | `none` ✗ | **`rollback`** ✓ |
| confidence | medium | medium | **high** |
| rounds / dispatches | 2 / 6 | 2 / 6 | 2 / 7 |
| services dispatched | checkout, **shipping**, quote | checkout only | checkout, currency, **shipping** ×3 |
| change-history id in evidence | no | an empty dependency query | **`tr_44a3bc84c6c0`, the image swap** |
| language boundary in narrative | no | n/a — shipping never queried | **yes** |
| contradiction flags | (check did not exist) | 1, false positive | 1, false positive |
| tokens | 45,015 | 48,526 | **52,175** |
| cost | $0.4829 | $0.4562 | **$0.5649** |
| re-asks | 2 of 10 | 4 of 10 | **1 of 11** (scribe only) |

Ground truth is `bad_deploy` / `rollback`. **Two of three match; the third is the only run at
high confidence and the only one to cite the change record.** n=3 is three observations, not a
rate.

### Did the planner's coverage reach shippingservice? Yes — three dispatches.

Round two:

    DISPATCH changes   shippingservice   deployments, config edits, or feature-flag changes ...
    DISPATCH metrics   shippingservice   request rate, error ratio, latency percentiles ...
    DISPATCH logs      shippingservice   what error or exception messages ... for GetQuote

T3.4b's planner reached the same trace conclusion and then dispatched neither shipping nor quote.
This one spent three of its seven dispatches there. **The contract is not the only difference
between the runs and cannot be credited alone** — but T3.4b's two wasted dispatches were the two
that packed service lists, and this run had none to waste.

### Did the change-history record reach the verdict's evidence? Yes, first in the list.

    evidence: ['tr_44a3bc84c6c0', 'tr_d9493cdf3ac9', 'tr_1836bbcbc2e0', 'tr_1749a639f99a',
               'tr_7d4b93d2d99c', 'tr_2e7b4cbd2305', 'tr_3d5cab00fe9e']

and the root cause opens on it: "At 02:53:58 UTC a platform-automation image-reference update
landed on shippingservice, replacing an unset/absent prior reference with an adservice-tagged
demo image (`tr_44a3bc84c6c0`)."

### Did the pre-onset language boundary reach the verdict and the narrative? Yes, both.

The verdict names it as a language change:

> "a Java process where shipping's normal (Rust-style) GetQuote/ShipOrder logging had been
> healthy until ~02:48"

and the narrative renders the contrast across the elision:

> "Through roughly 02:48 the stream shows ordinary INFO-level GetQuote and ShipOrder work. From
> 02:54:27 it contains only a repeating three-line JVM/OpenTelemetry-agent startup banner —
> restarts clustering at 02:54:27, 02:54:35, 02:54:46, then spacing to a steady ~65s cadence."

The envelope that carried it:

    <tool_result id="tr_d9493cdf3ac9" tool="logql_query" ... truncated="true"
      window="02:47:00..03:02:00" oldest_kept="8" newest_kept="32">

`incident.md` for this scenario calls that boundary the thing that separates a bad deploy from a
memory ceiling — "no resource limit does that". **T3.4 lost it to truncate-to-newest; T3.4b
restored the mechanism but never queried the service; T3.4c is the first run where it reached a
verdict.** The verdict is also the first to be `high` confidence, and this is the evidence it
rests on.

## The defect and the decision

`Dispatch.service` was a bare `str`. T3.4b's planner put four names in one field and a sentence
in another; the tool layer turned the first into a PromQL label value that cannot match any
`service_name`, and the specialist reported the result as empty. A dispatch now names exactly
one service the catalog knows, validated at plan-parse time, canonicalised in place, with the
same bounded re-ask and per-dispatch failure on a second miss. Recorded in **ADR-0020 §2**,
which had left the dispatch contract open; `docs/PLAN.md` carried the question and now points at
the answer.

Pinned with both verbatim strings from T3.4b's stored trajectory
(`tests/test_roles.py`). **The validator did not fire live** — this run's planner produced legal
single-service names on the first attempt in both rounds. That is the outcome the contract wants
and it is also, honestly, no evidence that the re-ask works in production; only the hermetic
pins test that path.

### One nuance the contract does not reach

The `service` **field** is now one legal name. The **question** is still prose, and one dispatch
shows the gap:

    DISPATCH metrics currencyservice  "Compare error rate, latency, saturation ... across
      adservice, cartservice, currencyservice, paymentservice, productcatalogservice and
      recommendationservice from 02:30 to 03:10 to find which degraded before 02:57."

The query that ran was well-formed and about `currencyservice` alone, so nothing malformed
reached Prometheus — the defect this task fixed did not recur. But the specialist was asked a
six-service question it could only answer for one. Constraining prose is a different problem from
constraining a field, and this is not it.

## A second defect, found by this run and fixed

**The first attempt at this smoke died before any tool ran.** The planner's reply was cut off at
`max_tokens` twice and the round was lost:

    SchemaValidationError: schema validation failed twice
      (Expecting ',' delimiter: line 1 column 2568 (char 2567))

Diagnosed before changing anything, by calling the planner directly against the same incident and
printing each attempt: `stop_reason=end_turn`, **915 output tokens against a 1200 cap**, five
dispatches, all services legal. The reply was not malformed and the services were not the
problem — the planner routinely runs at three-quarters of its budget and a slightly longer plan
truncates.

**This is exactly the defect T3.3 found for the specialists and fixed by raising 1200 → 3000.**
The planner kept the old cap. Raised to 3000, matching them. The re-run needed one re-ask in
eleven turns.

## The contradiction check: two live firings, both false positives

Recorded plainly because it matters for how much the flag can be trusted.

This run's firing:

    contradiction: the verdict says metrics was not queried for checkoutservice,
    and tr_7d4b93d2d99c is exactly that query

The sentence: *"No latency percentiles or per-downstream breakdown were retrieved for
checkoutservice (`tr_7d4b93d2d99c`), and no change history was gathered for checkoutservice's
other five dependencies ..."* — true of a metrics query that returned error ratio only, and **it
cites the very result it is describing**.

Fixed by a rule the id makes cheap: **a clause carrying a dispatch's own `result_id` is a claim
about that result, not a denial that it exists.** Re-run over all three stored verdicts after the
fix:

| run | before | after |
|---|---|---|
| T3.4 `e7739dec` | 1 — the real contradiction, `tr_f536225dc17d` | **1, unchanged** |
| T3.4b `6b9715de` | 1 — false positive | **0** |
| T3.4c `f7afdb76` | 1 — false positive | **0** |

**Live record so far: two firings, two false positives, zero true positives.** Its one true
positive is historical, from T3.4's stored verdict, and the assembly fix that shipped alongside
it removed that verdict's cause. Both false positives were caught by reading the run rather than
trusting the flag, and each produced a sharper rule. Whether the check ever fires correctly on a
run whose assembly is sound is still unmeasured, and T4.1's first batch is where that gets
answered.

## Retrieval and the leak guard

    exclude_origin='scenario:shipping-wrong-image'  k=3
    returned=['scenario:cart-redis-misconfig', 'scenario:cart-bad-image-tag', 'scenario:ad-memory-squeeze']

Unchanged across all three runs. Leak guard over the rendered narrative: **PASS**.

## Housekeeping

Reverted 03:10:09Z. Recovery confirmed 03:14:00Z: **0 active alerts**, checkoutservice and
frontend error ratios at 0.0000, all five previously-silent services serving (shippingservice
0.235, emailservice 0.348, quoteservice 0.157, accountingservice 0.078, frauddetectionservice
0.087 req/s). Ingest and orchestrator stopped.

`make check`: 311 passed, 1 skipped. Cost of this run: **$0.5649**, 52,175 tokens; the abandoned
first attempt and the direct planner diagnostic added roughly 4,000 more.
