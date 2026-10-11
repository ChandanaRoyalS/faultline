# Checkout failures traced to an unresolvable quote address on shipping

## What we saw first

Two alerts arrived together: shipping and checkout. The user-facing symptom was checkout failing for real traffic through the frontend proxy. Triage drew a blast radius of ten services with nine edges that had no measurement at all, and nominated shipping as the entry point. That framing turned out to be right, but almost everything that looked like a lead in the first few minutes was not.

The practical shape of the investigation: traces carried the whole answer, metrics were actively misleading, and logs for both alerting services were empty.

> Evidence `tr_3ffcfacdaf52`:

```
<tool_result id="tr_3ffcfacdaf52" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-08T12:47:16.664000+00:00..2026-10-08T13:20:14.266709+00:00">
service: shipping
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 292a68479dbc96bd  root load-generator/user_checkout_multi  55.0ms  started 2026-10-08T13:15:02.636643+00:00  26 spans
  +0.0ms load-generator/user_checkout_multi 55.0ms [self 39.6ms]
```

## Timeline as the responder experienced it

T+0 — alerts on shipping and checkout; checkout errors visible to users.

T+3m — pulled shipping's error ratio from span metrics expecting a step change at onset. Got the opposite: the incident-window average sat near 0.30 against a baseline near 0.38, i.e. lower, with no sustained departure flagged. Both windows swung across the full 0-to-1 range with standard deviations near 0.39, which reads as low or bursty span volume rather than a stable error level. The one useful thing this gave us is that shipping was already unhealthy before the window opened — there was no clean healthy-to-broken transition to find.

T+8m — went to shipping's logs to get the service to name its own failing dependency. Nothing. Not zero errors — zero lines, across the entire window including the thirty minutes of pre-onset baseline. Same story for checkout a few minutes later. An unfiltered selector on each service label matched nothing at all.

T+15m — traces. This is where it broke open. Every sampled checkout trace with a shipping leg shows shipping's inbound //get-quote handler returning Internal Server Error, and its entire error duration attributable to a single outbound child span targeting the quote dependency. That child fails with a resolver error — the name could not be looked up — in roughly 2 to 13 milliseconds. The propagation chain is clean and single-threaded: load-generator → frontend-proxy → frontend → checkout → shipping, with the deepest error at shipping's outbound leaf.

T+22m — change history for shipping. Seven environment-variable mutations in the window, all by the same automation actor, all touching one variable: QUOTE_ADDR. No code deploys, no image bumps, no other edits. The changes alternate set and revert roughly every 6 to 13 minutes across about an hour. The last action before onset, about two minutes prior, re-applied the set state pointing at a hostname that does not resolve.

> Evidence `tr_7139bd5665b4`:

```
<tool_result id="tr_7139bd5665b4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-08T12:47:16.664000+00:00..2026-10-08T13:20:14.266709+00:00" template="error-ratio" baseline="2026-10-08T12:14:19.061291+00:00..2026-10-08T12:47:16.664000+00:00">
service: shipping
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="shipping",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="shipping"}[5m]))
  incident window: n=132 mean=0.2991 min=0 max=1 sd=0.3941
  baseline window: n=112 mean=0.3767 min=0 max=1 sd=0.3829
```

> Evidence `tr_de28c03990c7`:

```
<tool_result id="tr_de28c03990c7" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-08T12:47:16.664000+00:00..2026-10-08T13:20:14.266709+00:00">
no log lines matched {service="shipping"} over this window
</tool_result:tr_de28c03990c7>
```

> Evidence `tr_ffd147f9c1e4`:

```
<tool_result id="tr_ffd147f9c1e4" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-08T12:47:16.664000+00:00..2026-10-08T13:20:14.266709+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_ffd147f9c1e4>
```

> Evidence `tr_3ffcfacdaf52`:

```
<tool_result id="tr_3ffcfacdaf52" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-08T12:47:16.664000+00:00..2026-10-08T13:20:14.266709+00:00">
service: shipping
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 292a68479dbc96bd  root load-generator/user_checkout_multi  55.0ms  started 2026-10-08T13:15:02.636643+00:00  26 spans
  +0.0ms load-generator/user_checkout_multi 55.0ms [self 39.6ms]
```

> Evidence `tr_49565a751401`:

```
<tool_result id="tr_49565a751401" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T13:17:16.664000+00:00..2026-10-08T13:20:14.266709+00:00" radius="seed" hops="0">
service: shipping
7 changes, ranked by suspicion
  #1  2m before onset  2026-10-08T13:14:20.403443+00:00  platform-automation  environment updated: QUOTE_ADDR updated on shipping
      None  ->  QUOTE_ADDR=http://quote-gone:8090
  #2  15m before onset  2026-10-08T13:01:39.312478+00:00  platform-automation  environment reverted: QUOTE_ADDR reverted on shipping
```

## Dead ends worth keeping

**Shipping's error-ratio metric as a detector.** We spent early minutes trying to reconcile a lower-than-baseline error ratio with a critical alert. The reconciliation is the flapping: shipping had been breaking a fraction of quote calls for the preceding hour, so the baseline was already contaminated. Don't expect this series to mark onset.

**Shipping and checkout logs.** Both streams are empty throughout, baseline included. We initially read shipping's silence as a crash or hang at onset — that shape would be a populated prefix followed by nothing, and that is not what is there. This is a collection or labelling gap, not service behaviour. Stop treating these as pending leads.

**Quote's own health.** Its span-call metrics return no samples in either window. We briefly treated the flatness as an all-clear and then as evidence that inbound traffic from shipping had stopped. Neither holds: a traffic stop would show samples before and none after. The series is empty throughout and carries no signal in either direction.

**Connection refused / quote returning 5xx.** Both ruled out by the error text itself. The failure is at name resolution, before any TCP connect is attempted, so no HTTP status from the dependency exists on any span.

**Shipping being slow or saturated.** Ruled out — failing spans complete in single-digit to low-teens milliseconds with near-zero self time on the handler. No latency buildup anywhere.

**Other checkout dependencies.** Currency, cart/Redis, product-catalog/SQL child spans all complete sub-millisecond to a few milliseconds with no error status in every trace examined. Only the shipping branch is marked ERROR.

**The email service.** The checkout span's error text blames a POST to an email service returning 500. No email-service span appears anywhere in any trace. We chased this for a while; it contradicts the child-span evidence directly.

**Frontend / frontend-proxy as origin.** Those spans carry ERROR only as inherited propagation with negligible self time.

**A human operator or a broad set of edits.** Every recorded change is attributed to the same automated actor, and all seven touch one key. The surface that moved is one variable wide.

> Evidence `tr_7139bd5665b4`:

```
<tool_result id="tr_7139bd5665b4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-08T12:47:16.664000+00:00..2026-10-08T13:20:14.266709+00:00" template="error-ratio" baseline="2026-10-08T12:14:19.061291+00:00..2026-10-08T12:47:16.664000+00:00">
service: shipping
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="shipping",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="shipping"}[5m]))
  incident window: n=132 mean=0.2991 min=0 max=1 sd=0.3941
  baseline window: n=112 mean=0.3767 min=0 max=1 sd=0.3829
```

> Evidence `tr_de28c03990c7`:

```
<tool_result id="tr_de28c03990c7" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-08T12:47:16.664000+00:00..2026-10-08T13:20:14.266709+00:00">
no log lines matched {service="shipping"} over this window
</tool_result:tr_de28c03990c7>
```

> Evidence `tr_ffd147f9c1e4`:

```
<tool_result id="tr_ffd147f9c1e4" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-08T12:47:16.664000+00:00..2026-10-08T13:20:14.266709+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_ffd147f9c1e4>
```

> Evidence `tr_10d0986ac8a1`:

```
<tool_result id="tr_10d0986ac8a1" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-08T12:47:16.664000+00:00..2026-10-08T13:20:14.266709+00:00" template="error-ratio" baseline="2026-10-08T12:14:19.061291+00:00..2026-10-08T12:47:16.664000+00:00">
service: quote
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="quote",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="quote"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_3ffcfacdaf52`:

```
<tool_result id="tr_3ffcfacdaf52" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-08T12:47:16.664000+00:00..2026-10-08T13:20:14.266709+00:00">
service: shipping
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 292a68479dbc96bd  root load-generator/user_checkout_multi  55.0ms  started 2026-10-08T13:15:02.636643+00:00  26 spans
  +0.0ms load-generator/user_checkout_multi 55.0ms [self 39.6ms]
```

> Evidence `tr_49565a751401`:

```
<tool_result id="tr_49565a751401" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T13:17:16.664000+00:00..2026-10-08T13:20:14.266709+00:00" radius="seed" hops="0">
service: shipping
7 changes, ranked by suspicion
  #1  2m before onset  2026-10-08T13:14:20.403443+00:00  platform-automation  environment updated: QUOTE_ADDR updated on shipping
      None  ->  QUOTE_ADDR=http://quote-gone:8090
  #2  15m before onset  2026-10-08T13:01:39.312478+00:00  platform-automation  environment reverted: QUOTE_ADDR reverted on shipping
```

## The cause

Shipping's QUOTE_ADDR environment variable was pointed at a hostname that does not resolve, re-applied roughly two minutes before onset by an automation actor that had been flapping this single variable set/revert every 6 to 13 minutes for the preceding hour. Shipping entered the incident in the set state.

The wrongness of the value is itself the mechanism. Every outbound quote call from shipping dies at the resolver in milliseconds with a name-not-known error; the request never leaves the process. Shipping's //get-quote handler returns Internal Server Error and that propagates up checkout → frontend → frontend-proxy to the user-facing failures. Nothing about the quote service's health, capacity or latency is implicated, because nothing ever reached it.

Confidence: high. Fix class: revert the variable to its correct value.

> Evidence `tr_49565a751401`:

```
<tool_result id="tr_49565a751401" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T13:17:16.664000+00:00..2026-10-08T13:20:14.266709+00:00" radius="seed" hops="0">
service: shipping
7 changes, ranked by suspicion
  #1  2m before onset  2026-10-08T13:14:20.403443+00:00  platform-automation  environment updated: QUOTE_ADDR updated on shipping
      None  ->  QUOTE_ADDR=http://quote-gone:8090
  #2  15m before onset  2026-10-08T13:01:39.312478+00:00  platform-automation  environment reverted: QUOTE_ADDR reverted on shipping
```

> Evidence `tr_3ffcfacdaf52`:

```
<tool_result id="tr_3ffcfacdaf52" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-08T12:47:16.664000+00:00..2026-10-08T13:20:14.266709+00:00">
service: shipping
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 292a68479dbc96bd  root load-generator/user_checkout_multi  55.0ms  started 2026-10-08T13:15:02.636643+00:00  26 spans
  +0.0ms load-generator/user_checkout_multi 55.0ms [self 39.6ms]
```

## Still open

The correct value of QUOTE_ADDR was never confirmed. One recorded revert state reads a port of :809 rather than :8090, so the so-called good state in the change log may itself be malformed. Verify before reverting.

Why the automation is flapping this one variable on a 6-to-13-minute cycle is unexplained. A plain revert will likely be overwritten on the next reconciliation pass — address the loop, not just the value.

Quote's own health is entirely unmeasured. We cannot confirm a healthy quote service exists behind the correct address.

Neither shipping nor checkout ever stated the problem in its own words; the resolver attribution rests solely on trace error text. If that text is wrong, we have no corroboration.

The email-service wording on the checkout span is unsettled — stale or hardcoded error text, or a second masked failure path. Worth a look if symptoms persist after the revert.

One trace near the end of the onset window shows the same user-facing checkout failure with only eight spans, ending at frontend gRPC PlaceOrder with roughly 49ms of self time and no checkout or shipping children at all. Not every failing request has been shown to follow the quote-resolution chain.

Seven of the ten services in the reported blast radius were never examined by anyone. Collateral or unrelated impact across those nine unmeasured edges is unassessed.

> Evidence `tr_49565a751401`:

```
<tool_result id="tr_49565a751401" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T13:17:16.664000+00:00..2026-10-08T13:20:14.266709+00:00" radius="seed" hops="0">
service: shipping
7 changes, ranked by suspicion
  #1  2m before onset  2026-10-08T13:14:20.403443+00:00  platform-automation  environment updated: QUOTE_ADDR updated on shipping
      None  ->  QUOTE_ADDR=http://quote-gone:8090
  #2  15m before onset  2026-10-08T13:01:39.312478+00:00  platform-automation  environment reverted: QUOTE_ADDR reverted on shipping
```

> Evidence `tr_10d0986ac8a1`:

```
<tool_result id="tr_10d0986ac8a1" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-08T12:47:16.664000+00:00..2026-10-08T13:20:14.266709+00:00" template="error-ratio" baseline="2026-10-08T12:14:19.061291+00:00..2026-10-08T12:47:16.664000+00:00">
service: quote
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="quote",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="quote"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_de28c03990c7`:

```
<tool_result id="tr_de28c03990c7" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-08T12:47:16.664000+00:00..2026-10-08T13:20:14.266709+00:00">
no log lines matched {service="shipping"} over this window
</tool_result:tr_de28c03990c7>
```

> Evidence `tr_ffd147f9c1e4`:

```
<tool_result id="tr_ffd147f9c1e4" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-08T12:47:16.664000+00:00..2026-10-08T13:20:14.266709+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_ffd147f9c1e4>
```

> Evidence `tr_3ffcfacdaf52`:

```
<tool_result id="tr_3ffcfacdaf52" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-08T12:47:16.664000+00:00..2026-10-08T13:20:14.266709+00:00">
service: shipping
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 292a68479dbc96bd  root load-generator/user_checkout_multi  55.0ms  started 2026-10-08T13:15:02.636643+00:00  26 spans
  +0.0ms load-generator/user_checkout_multi 55.0ms [self 39.6ms]
```

