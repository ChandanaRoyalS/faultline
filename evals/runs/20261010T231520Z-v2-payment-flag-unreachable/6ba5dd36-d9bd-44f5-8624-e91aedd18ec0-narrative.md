# Checkout order failures traced to a silent payment process

## What was visible, in order

Five services alerted together, with checkout named as the entry point and twelve services in the blast radius. The first instinct was that checkout had broken: it is closest to the user and it is the one with a change history. That instinct cost time.

Checkout's own signals said little. Its aggregate error ratio averaged about 0.090 during the window against 0.072 in the preceding half hour, but the spread is as large as the mean in both periods and the maxima are effectively identical (0.2157 versus 0.2203) — no sustained departure, and a baseline that was already noisy before anything happened. Only the error-ratio template returned data, aggregated by service name alone, so it could neither accuse nor exonerate any downstream. A log query on the checkout service label returned zero lines across the entire window, including the healthy stretch, so this is a label or shipping gap rather than a service going quiet at onset. Checkout's client-side view of the failure is therefore unavailable; everything below comes from traces.

Traces settled it. From roughly T-1m onward, every sampled checkout trace fails in PaymentService/Charge with a gRPC Unavailable name-resolution error returning zero addresses. The span carries about 0.0ms duration and 0% of trace time. A slow backend produces a long span ending in a timeout; a zero-duration resolution failure means the client never got an address and never opened a connection. The error propagates unchanged up through frontend, proxy and load generator. End-to-end latency stayed in the tens of milliseconds throughout — this is an availability incident, not a slowdown.

Payment's own logs corroborate. The query came back truncated, but the newest retained line sits about four and a half minutes before onset and is a normal info-level, trace-correlated transaction completion. After it, nothing: no shutdown, no crash, no listen or bind record. Host identity, runtime and service version are unchanged across the window, so no replacement instance appeared. A process that stopped doing work without exiting cleanly drops out of discovery, and callers fail fast on resolution — which is exactly what checkout shows.

> Evidence `tr_c73ae4c5dcef`:

```
<tool_result id="tr_c73ae4c5dcef" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-10T22:49:46.664000+00:00..2026-10-10T23:23:44.279941+00:00" template="error-ratio" baseline="2026-10-10T22:15:49.048059+00:00..2026-10-10T22:49:46.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=136 mean=0.08972 min=0 max=0.2157 sd=0.09136
  baseline window: n=136 mean=0.07157 min=0 max=0.2203 sd=0.09072
```

> Evidence `tr_f4248832d4ea`:

```
<tool_result id="tr_f4248832d4ea" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-10T22:49:46.664000+00:00..2026-10-10T23:23:44.279941+00:00">
service: checkout
6 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 697a8d044a28f9b6  root load-generator/user_checkout_multi  65.6ms  started 2026-10-10T23:18:51.729238+00:00  42 spans
  +0.0ms load-generator/user_checkout_multi 65.6ms [self 35.1ms]
```

> Evidence `tr_041fbef7b9d5`:

```
<tool_result id="tr_041fbef7b9d5" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-10T22:49:46.664000+00:00..2026-10-10T23:23:44.279941+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment"}
2026-10-10T22:49:46.971928+00:00  {
2026-10-10T22:49:46.971951+00:00    resource: {
2026-10-10T22:49:46.971953+00:00      attributes: {
2026-10-10T22:49:46.971954+00:00        'process.pid': 1,
```

## Dead ends worth keeping

Checkout's change log showed eight entries, all from the same automated actor, all touching one environment variable — the currency service address — in four identical set/revert pairs. Flapping, not a rollout, and it left the variable unset entering the incident. It is not the cause: every entry is at least 16.5 hours before onset, the log is empty for those final 16.5 hours, there is no deploy or release for checkout anywhere in the window, and the traces show currency healthy throughout. Hygiene finding, not explanation.

Payment's change log is the more attractive trap. Eight entries, same automated actor, all a traffic-shaping sidecar attached to and removed from payment's network namespace, each attach applying a fixed 300ms egress delay on eth0, cycling four times over about seventy minutes. A 300ms delay on payment is exactly the sort of thing that breaks checkout — but the whole cluster sits 22–23 hours before onset, the last event is a removal, and payment ran unshaped for the ~22 hours leading in. The trace signature is also wrong for it: shaping makes spans slow, and this span has no duration at all. The same log shows no deploy, no identity or port edit, no scaling and no restart for payment.

Flag configuration was queried across one hop and returned nothing, and no flag-evaluation span appears in any sampled trace. Note a defect in how that query was framed: its window begins at onset and runs forward, so it says nothing about the hours before.

Also cleared in the same traces, so nobody re-walks them: cart and its Redis backing (1–2.4ms, error-free), currency conversion (a few ms per call), product catalog and its SQL children (sub-millisecond to a few ms), and shipping quotes (1–8ms). Payment was the only errored downstream in every trace.

> Evidence `tr_08b3cdb0176e`:

```
<tool_result id="tr_08b3cdb0176e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-09T23:19:46.664000+00:00..2026-10-10T23:23:44.279941+00:00" radius="seed" hops="0">
service: checkout
8 changes, ranked by suspicion
  #1  16.5h before onset  2026-10-10T06:47:58.823426+00:00  platform-automation  environment reverted: CURRENCY_ADDR reverted on checkout
      CURRENCY_ADDR=currencyservice:7001  ->  None
  #2  16.7h before onset  2026-10-10T06:39:40.851789+00:00  platform-automation  environment updated: CURRENCY_ADDR updated on checkout
```

> Evidence `tr_352f01e4dff7`:

```
<tool_result id="tr_352f01e4dff7" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-09T23:19:46.664000+00:00..2026-10-10T23:23:44.279941+00:00" radius="seed" hops="0">
service: payment
8 changes, ranked by suspicion
  #1  22.1h before onset  2026-10-10T01:14:13.647748+00:00  platform-automation  container removed: traffic-shaping container removed from payment's network namespace
      eth0 delay=300ms jitter=0ms  ->  None
  #2  22.2h before onset  2026-10-10T01:06:57.981995+00:00  platform-automation  container created: traffic-shaping container attached to payment's network namespace
```

> Evidence `tr_9bb8622d2b41`:

```
<tool_result id="tr_9bb8622d2b41" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-09T23:19:46.664000+00:00..2026-10-10T23:23:44.279941+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_9bb8622d2b41>
```

## Conclusion, confidence and what is still open

Payment went silent mid-window on an ordinary successful transaction, with no exit or re-bind record and unchanged process identity. About four minutes later every checkout trace fails at payment name resolution with no connection attempted. Fix class is a restart of payment. Confidence is medium, not high, and the gaps are the reason.

What is unresolved. No payment-side evidence distinguishes a stalled process from a payment instance severed from the network — the logs were truncated and the final minutes are empty, so we never saw whether payment itself complained about unreachable peers. Payment's span-metrics series is empty across both the incident and baseline windows, so its request rate and latency were never measured and its liveness cannot be confirmed independently; note that this absence predates onset and is a pipeline gap, not a symptom, and the 'no departure from baseline' verdict for payment must not be read as a clean bill of health. Checkout emitted no logs at all, so its view of the resolution failures is unverified outside traces. Finally, nobody examined service discovery or DNS directly, which is the other plausible source of a resolution failure returning zero addresses — that is where a future responder should start.

> Evidence `tr_2cea50f0ea84`:

```
<tool_result id="tr_2cea50f0ea84" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-10T22:49:46.664000+00:00..2026-10-10T23:23:44.279941+00:00" template="error-ratio" baseline="2026-10-10T22:15:49.048059+00:00..2026-10-10T22:49:46.664000+00:00">
service: payment
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="payment",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="payment"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_041fbef7b9d5`:

```
<tool_result id="tr_041fbef7b9d5" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-10T22:49:46.664000+00:00..2026-10-10T23:23:44.279941+00:00" oldest_kept="8" newest_kept="32">
selector: {service="payment"}
2026-10-10T22:49:46.971928+00:00  {
2026-10-10T22:49:46.971951+00:00    resource: {
2026-10-10T22:49:46.971953+00:00      attributes: {
2026-10-10T22:49:46.971954+00:00        'process.pid': 1,
```

> Evidence `tr_77a8b350df33`:

```
<tool_result id="tr_77a8b350df33" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-10T22:49:46.664000+00:00..2026-10-10T23:23:44.279941+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_77a8b350df33>
```

