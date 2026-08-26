# T3.4b re-run — same scenario, same pipeline, two defects fixed

`shipping-wrong-image` again, injected 02:23:56Z and reverted 02:37:37Z. Same world, same
model, same budget as T3.4's second pass. `investigation.txt` is the run as captured;
`narrative.md` is the rendered narrative alone.

This is also the **first time a scenario has been run twice**, so the two verdicts below are the
project's first variance observation. They are not a comparison of a fix against a control —
the fixes changed the tool layer and the briefs, and the world's alert set differed between
runs. What follows is what each run produced, side by side.

## Baseline before injection, checked explicitly

Still no gate on this path (the T4.1 note in `docs/PLAN.md`). Checked by hand at 02:21:47Z:

- **0 active alerts** in Alertmanager
- **no service** with p95 over 1000ms — T3.4's pre-run degradation signature (checkoutservice
  and frontend pinned at 15000ms) absent
- 15 services reporting; one at 0.000 req/s, `frontend-proxy`

`frontend-proxy` at zero is **the clean state, not a fault.** The committed clean baseline
`evals/baselines/20260824T033742Z` records it at 181 consecutive samples of 0.0, min and max
alike — it emits `calls_total` with a zero rate always. No repair was applied; the world was
clean as found.

One piece of state did need clearing: T3.4's incident `fb7ad21e` was still `triaging`, and
TimeOverlapPolicy would have joined the new alerts to it rather than opening a new incident.
Removed by disclosed SQL (8 `incident_episodes`, 9 `applied_events`, 1 `incidents`), and ingest
and orchestrator were run on a fresh stream and group (`faultline:t34b` / `t34b`).

## The two verdicts, side by side

| | **T3.4** (trajectory `e7739dec`) | **T3.4b** (trajectory `6b9715de`) |
|---|---|---|
| incident | 8 episodes / 7 services | 7 episodes |
| triage | 12 services, critical, start from checkoutservice, 5 unmeasured edges | identical |
| rounds / dispatches | 2 / 6 | 2 / 6 |
| services dispatched | checkoutservice, **shippingservice**, quoteservice | checkoutservice **only** (plus one dependency list) |
| fault class | **`bad_deploy`** | **`unknown`** |
| fix class | **`rollback`** | **`none`** |
| confidence | **medium** | **medium** |
| evidence cited | `tr_8657d00962e4`, `tr_2ccf8bd687ef`, `tr_bf1ed807067d`, `tr_1c0655065fe4` | `tr_74791dcc5b78`, `tr_04ef8cf2aed4`, `tr_cd8b667857a0` |
| flags | none | one contradiction (a false positive — below) |
| tokens | 45,015 | **48,526** |
| cost | $0.4829 | **$0.4562** |
| re-asks | 2 of 10 turns | 4 of 10 turns (planner, logs, synthesizer, scribe) |

Ground truth is `bad_deploy` / `rollback`. **T3.4 matched it; T3.4b did not.**

### Why, and it is not the fixes

T3.4's round-two planner dispatched change history and logs **at shippingservice**, on trace
evidence that `ShippingService/GetQuote` was the erroring leaf. T3.4b's planner reached the same
trace conclusion — its narrative is titled "Checkout aborts at the shipping-quote hop" and its
root cause localizes the failure to exactly that hop — and then **dispatched neither shipping
nor quote**. Round two went to traces, a dependency-list metrics query, and a dependency-list
change query, all anchored on checkoutservice.

Its verdict says so plainly, and its first open question is: "shippingservice and quoteservice
were never dispatched — their changes, metrics, logs and restart/OOM state are wholly
unexamined." Having localized the hop, it classified `unknown` rather than guessing, which is
the behaviour the schema is meant to produce; it simply never spent a dispatch on the service it
had named.

**So the answer to "does the verdict's evidence list now include the change-history result_id"
is: a change-history id is cited (`tr_cd8b667857a0`), but it is the empty dependency-list query,
not a shippingservice change record — because no shippingservice change record was ever
fetched.** The assembly fix cannot be credited or blamed here: with one dispatch per specialist
per service and no repeated (specialist, service) pair collapsing, T3.4's dict-keyed assembly
would have delivered the same six runs.

Two runs, one match and one miss, on identical triage input. That is the variance, stated
without a model of it: n=2 is an observation, not a rate.

## Defect 1 — the synthesizer's contradiction

### Diagnosis, before any fix

Read from trajectory `e7739dec` directly. `InvestigationResult.findings` was
`{run.specialist: run.findings for run in self.runs}` — a dict keyed on specialist name. T3.4
ran `changes` three times:

```
changes  checkoutservice   tr_81afb255f44e   2 found
metrics  checkoutservice   tr_bf1ed807067d   3 found
traces   checkoutservice   tr_8657d00962e4   6 found
changes  shippingservice   tr_f536225dc17d   4 found   <- the ground truth, named outright
changes  quoteservice      tr_1c0655065fe4   2 found   <- empty result, and the last writer
logs     shippingservice   tr_2ccf8bd687ef   5 found
```

The comprehension kept the last `changes` run. `tr_f536225dc17d` and `tr_81afb255f44e` were
**dropped before the synthesizer was called**.

**It was a context-assembly defect, not an attention defect.** The verdict's claim that "the
changes specialist queried quoteservice, not shippingservice" was accurate about what it was
shown. The brief compounded it: findings were labelled `[changes]` with no service, so three
dispatches over three services were indistinguishable even in principle.

### Fixed

Every executed dispatch now reaches the planner's follow-up brief, the synthesizer's brief and
the scribe's brief, each labelled `specialist on service` and carrying its `result_id`. The
synthesizer's brief opens with a one-line-per-dispatch index before the detail, so what was
queried is stated before what was found.

### And the cross-check, which found a live false positive

The deterministic check was added anyway, for the case the assembly fix does not cover. It
fired on this run:

    contradiction: the verdict says changes was not queried for checkoutservice,
    and tr_8deedf529f24 is exactly that query

**It was wrong.** The sentence is:

> "Why shippingservice/quoteservice is refusing these calls is unestablished: no dispatch
> examined either service, and the empty change results covered only checkoutservice plus five
> other dependencies over 02:17-02:32."

Two halves. The first says shipping and quote were never dispatched — true. The second says
checkoutservice *was* covered. The clause splitter broke on sentence ends and dashes but not on
comma-plus-conjunction, so the negation in the first half reached the service named in the
second. Fixed by adding `, and` / `, but` / `, so` and their kin to the clause break, and pinned
with the sentence verbatim (`tests/test_grounding.py`). Re-run against the stored verdict after
the fix: **no contradiction reported.**

A check that cries wolf is worse than no check, so this is worth stating flatly: the check's
first live firing was a false positive, and it was caught only because the run was read rather
than trusted.

## Defect 2 — truncate-to-newest

Log retention is now two-ended: the newest majority of the budget plus a small oldest sample,
an explicit elision marker between them, and both counts in the envelope. Sizes are a fifth of
the budget, floored at 3 and ceilinged at 8 (ADR-0021 §4). At the specialist's `limit=40` that
is 8 and 32.

Live, on this run:

    <tool_result id="tr_04ef8cf2aed4" tool="logql_query" ... truncated="true"
      window="02:17:00..02:32:00" oldest_kept="8" newest_kept="32">
    ...
      ... lines between here and the next timestamp were not returned: this result keeps
      the OLDEST 8 and the NEWEST 32 lines of the window, and nothing in between ...

**The specialist read it correctly and said so**, which is the change that matters:

> "The query for checkoutservice logs over 02:17–02:32 returned lines but was truncated: only
> the oldest 8 (02:17:02–02:17:12) and newest 32 (02:28:36–02:31:56) lines were kept, so roughly
> 02:17–02:28 is unverified."

Compare T3.4, where the same tool's silence was reported as fact: "the service emitted nothing
for the first ~7 minutes."

**And it used the two ends as a comparison**, which is what the shape was for:

> "In the early part of the window each order shows a full lifecycle: order start, payment
> success, confirmation email, and a successful queue write ... In the last ~3.5 minutes
> (02:28:36 onward) only order-start lines appear — the payment, email-confirmation, and
> queue-write completion lines that accompanied earlier orders are entirely absent."

A before/after finding the one-ended envelope could not have supported.

### What was *not* exercised live

**The pre-onset language boundary was not tested by this run.** The signal the change was built
for — Rust request logs before the boundary, JVM banners after it — lives in shippingservice's
logs, and this run never queried shippingservice. The two-ended envelope did real work on
checkoutservice instead.

That boundary is pinned hermetically instead, against the committed capture
(`evals/scenarios/artifacts/dev/shipping-wrong-image/logs/shipping-service.txt`, 299 lines
spanning 18:24:29–18:39:14) replayed through a Loki double that honours `direction` and `limit`
the way the real server does. The test asserts the oldest group contains `ShipOrderRequest` and
no `javaagent`, the newest contains `javaagent` and no `ShipOrderRequest`, and both counts and
the marker appear in the rendered envelope. The old T2.6 fake ignored both parameters, which is
why it could not have caught this: the whole defect lives in which lines the server chooses
before the client sees any.

### T2.6's pins

- **Direction pin** (`the loki request asks for the newest lines`): unchanged, passes.
- **Trace truncation pin**: unchanged, passes. Traces were not touched — the defect was in log
  content and the 200-span cap has not been measured against the same argument.
- **Newest-lines pin**: **amended, intent intact.** Its numbers moved because the behaviour it
  pinned is what was deliberately changed. It still asserts a truncated result is dominated by
  the end of the window (7 of 10 lines), still asserts the middle is dropped, and now also
  asserts the split counts. The failure it exists to prevent — a truncated result containing
  nothing but pre-onset traffic — is still prevented.

## Retrieval and the leak guard

One `trajectory_retrievals` row, unchanged in behaviour:

    exclude_origin='scenario:shipping-wrong-image'  k=3
    returned=['scenario:cart-redis-misconfig', 'scenario:cart-bad-image-tag', 'scenario:ad-memory-squeeze']

Leak guard over the rendered narrative: **PASS**.

## A separate observation, not fixed here

The planner passed **comma-separated service lists** where a single service belongs —
`"paymentservice, currencyservice, cartservice, productcatalogservice"` reached the tool layer
as one `service` value. The resulting PromQL matched no series at all, and the metrics
specialist reported an empty result. The synthesizer's scribe caught it and made it the
narrative's dead-end section:

> "The selector packed all four service names into a single label value, which cannot match any
> individual `service_name` label, so it matched no series at all — not even the denominator of
> total calls. A genuine zero-error condition would still have produced a series with a zero
> numerator."

Two dispatches of six were spent this way. The dispatch schema does not constrain `service` to
one name and the tool layer does not reject a list. Recorded, not fixed — it is a dispatch
contract question, and `docs/PLAN.md` carries it as a T4 note.

## Housekeeping

Reverted 02:37:37Z. Recovery confirmed 02:41:12Z: **0 active alerts**, checkoutservice and
frontend error ratios at 0.0000, all five previously-silent services serving (shippingservice
0.313, emailservice 0.383, quoteservice 0.209, accountingservice 0.104, frauddetectionservice
0.096 req/s). Ingest and orchestrator stopped.

`make check`: see the branch. Cost of this run: **$0.4562**, 48,526 tokens.
