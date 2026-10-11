# Checkout PlaceOrder failures traced to unreachable cart backend

## What we saw first

The page came in as critical, with checkout named as the origin and alerts firing simultaneously on frontend, frontend-proxy, load-generator and fraud-detection. The blast radius counted fifteen services, but the alert fan-out is misleading: most of those services are on the same request path and were reporting the same single failure from different altitudes.

The first thing worth doing was pinning onset. Checkout's error ratio had a flat, zero-variance baseline for the half hour before the event and crossed threshold at roughly T+2m, with a second crossing around T+23m. Mean error ratio during the window sat near 17% with peaks around 67% and dips back to zero, so checkout was never fully down — it was failing a fraction of requests in bursts. Two crossings and a standard deviation larger than the mean argue for an intermittent or relapsing pattern rather than one unbroken outage. Note that the metric onset is well before the timestamp the page was anchored to; anyone hunting correlated events at the page time is looking roughly twenty minutes too late.

> Evidence `tr_3e612efe4cf5`:

```
<tool_result id="tr_3e612efe4cf5" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-07T00:45:46.664000+00:00..2026-10-07T01:17:43.212287+00:00" template="error-ratio" baseline="2026-10-07T00:13:50.115713+00:00..2026-10-07T00:45:46.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=128 mean=0.1696 min=0 max=0.6667 sd=0.2531
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

## Where the error actually originates

Ten sampled failing traces all bottom out in the same place: checkout's outbound gRPC call to cart's GetCart, made from the prepareOrderItemsAndShippingQuoteFromCart step. That span carries the deepest ERROR status, with a gRPC name-resolver message reporting zero addresses. Checkout's own PlaceOrder server span wraps the same condition and reports Unavailable; frontend's client span, the /api/checkout route handler, frontend-proxy's ingress and egress, and the load-generator POST are all ERROR purely by inheritance.

The timing inside the traces is the useful detail. The failing GetCart spans complete in roughly zero to three tenths of a millisecond, and whole traces finish in under about 62ms. Nothing accumulates latency anywhere. These are immediate refusals before a connection is attempted, not slow calls and not deadline expiry.

Sampling caveat: the returned traces cluster around T+23m and T+24m to T+25m. None fell into the earlier burst near T+2m, so that first episode is not directly characterized by trace evidence.

> Evidence `tr_96e693bfbb47`:

```
<tool_result id="tr_96e693bfbb47" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-07T00:30:46.664000+00:00..2026-10-07T01:17:43.212287+00:00">
service: checkout
10 trace(s) shown of 10 found, 110 spans; offsets are from each trace's root

trace 4aeb23ecdaad91e6  root load-generator/user_checkout_multi  17.0ms  started 2026-10-07T01:13:36.095629+00:00  11 spans
  +0.0ms load-generator/user_checkout_multi 17.0ms [self 12.5ms]
```

## How the failure evolved

Frontend logs are what turn a snapshot into a sequence. The earliest checkout-path errors appear at roughly T+0 as gRPC INTERNAL wrapping an Unavailable cart RPC, and the underlying detail at that stage is a TCP dial timeout to a concrete cart endpoint — a specific address and port, already resolved. Later in the window the character changes: host-unreachable connect errors against that same address, and only after that the resolver results reporting zero addresses.

That ordering matters. If service discovery had been the first thing to go, there would never have been a concrete address to dial. Instead the address resolved fine and the dial failed, then the connect failed outright, then the endpoint list emptied. Discovery emptiness is a consequence here, not the trigger. Errors persist across roughly 27 minutes; the latest embedded connect-failure timestamp inside the error details lands near T+25m, so some of the trailing log lines may be replays of a cached last-error rather than fresh attempts.

Every error string in the window names the cart retrieval step. No other downstream of checkout appears.

> Evidence `tr_2c30aa0ffbbb`:

```
<tool_result id="tr_2c30aa0ffbbb" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T00:30:46.664000+00:00..2026-10-07T01:17:43.212287+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-07T00:50:58.147704+00:00  Error: 13 INTERNAL: cart failure: failed to get user cart during checkout: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing: dial tcp 172.18.0.24:7070: i/o timeout"
2026-10-07T00:50:58.148063+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-07T00:50:58.148067+00:00      at new Promise (<anonymous>) {
2026-10-07T00:50:58.148068+00:00    code: 13,
```

## Dead ends

These consumed time and found nothing, which is exactly why they belong in the record.

First, checkout's change history. A full-day query returned no records at all for checkout at zero hops — no release, no config edit, no flag flip. That rules out release reversal as a remediation path for this service; there is nothing to revert.

Second, flagd. It was queried twice, by two different paths, and came back empty both times. Worth knowing before you re-run it a third time: the window used begins at the reference timestamp and runs forward about twenty-four hours, so it covers during-and-after but not the hours before onset. The empty result is therefore strong evidence that nothing changed during or after, and weak evidence about what preceded it.

Third, and most annoying: checkout's own logs. A query on the checkout service label over the full 32-minute window returned no lines of any severity — not zero errors, zero output. The emptiness spans the thirty minutes of lead-in too, so it is not a windowing artifact and narrowing the range will not recover anything. Two readings stayed open and were never separated: checkout genuinely emitted nothing under that identity, or it logged normally and the lines are unreachable under the queried label because of a label mismatch, a shipping break, or retention. Any narrative that wants to rest on a checkout error message has no support from this source.

> Evidence `tr_5276b09e3342`:

```
<tool_result id="tr_5276b09e3342" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-06T01:15:46.664000+00:00..2026-10-07T01:17:43.212287+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_5276b09e3342>
```

> Evidence `tr_d61ac96cbf88`:

```
<tool_result id="tr_d61ac96cbf88" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-06T01:15:46.664000+00:00..2026-10-07T01:17:43.212287+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_d61ac96cbf88>
```

> Evidence `tr_1d401fdc8d70`:

```
<tool_result id="tr_1d401fdc8d70" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-06T01:15:46.664000+00:00..2026-10-07T01:17:43.212287+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_1d401fdc8d70>
```

> Evidence `tr_bc6f0dcbc518`:

```
<tool_result id="tr_bc6f0dcbc518" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-07T00:45:46.664000+00:00..2026-10-07T01:17:43.212287+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_bc6f0dcbc518>
```

## What we concluded

Checkout is where the failure surfaced, not where it began. Callers could not reach cart at the network layer: a previously-good endpoint stopped accepting connections, then became unreachable, then dropped out of the endpoint list entirely. Cart's application logic was never exercised — no request arrived — so empty-cart, bad-user-id and auth-rejection explanations are all off the table, as are overload and timeout stories given the sub-millisecond failures.

The fix class is reconnect: restore reachability to cart and get its endpoints re-registered. Confidence is medium, and the reason it is not higher is stated plainly in the next section.

> Evidence `tr_96e693bfbb47`:

```
<tool_result id="tr_96e693bfbb47" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-07T00:30:46.664000+00:00..2026-10-07T01:17:43.212287+00:00">
service: checkout
10 trace(s) shown of 10 found, 110 spans; offsets are from each trace's root

trace 4aeb23ecdaad91e6  root load-generator/user_checkout_multi  17.0ms  started 2026-10-07T01:13:36.095629+00:00  11 spans
  +0.0ms load-generator/user_checkout_multi 17.0ms [self 12.5ms]
```

> Evidence `tr_2c30aa0ffbbb`:

```
<tool_result id="tr_2c30aa0ffbbb" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T00:30:46.664000+00:00..2026-10-07T01:17:43.212287+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-07T00:50:58.147704+00:00  Error: 13 INTERNAL: cart failure: failed to get user cart during checkout: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing: dial tcp 172.18.0.24:7070: i/o timeout"
2026-10-07T00:50:58.148063+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-07T00:50:58.148067+00:00      at new Promise (<anonymous>) {
2026-10-07T00:50:58.148068+00:00    code: 13,
```

> Evidence `tr_3e612efe4cf5`:

```
<tool_result id="tr_3e612efe4cf5" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-07T00:45:46.664000+00:00..2026-10-07T01:17:43.212287+00:00" template="error-ratio" baseline="2026-10-07T00:13:50.115713+00:00..2026-10-07T00:45:46.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=128 mean=0.1696 min=0 max=0.6667 sd=0.2531
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

## Still open

No one queried cart itself. That is the single largest gap. Cart's own log is precisely what distinguishes a live process complaining that it cannot reach anything from a process that died or was restarting — from the caller's chair both look identical.

Relatedly, whether cart's endpoint count fell to zero because readiness checks began failing or because the instance terminated is unresolved. Both produce the same caller-side resolver message, and nothing gathered here separates them.

Finally, the 32-minute silence in checkout's logs was never explained. If it is an ingestion or labeling artifact, fix it before the next event; if it is real, it is a second finding hiding behind the first.

> Evidence `tr_bc6f0dcbc518`:

```
<tool_result id="tr_bc6f0dcbc518" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-07T00:45:46.664000+00:00..2026-10-07T01:17:43.212287+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_bc6f0dcbc518>
```

