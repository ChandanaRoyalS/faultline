# Checkout failures trace to the cart dependency edge

## What we saw first

The page opened on frontend: checkout requests were failing for a fraction of users, with loadgenerator and checkoutservice alerting alongside. The first thing worth knowing is that frontend's aggregate error ratio had been *exactly* zero for the whole 32-minute pre-incident stretch — 129 samples, zero mean, zero max, zero spread. So this was not a degradation of an already-imperfect baseline; it was a clean transition from no errors at all into a window averaging roughly 5% with peaks near 30%. Majority of traffic still succeeded throughout, which is why the symptom read as intermittent checkout failure rather than an outage.

One detail from that first look mattered much more later than it did at the time: the frontend query aggregated by service name only, with no peer or backend dimension. It told us frontend was erroring and told us nothing about which downstream was responsible. Do not spend time re-reading it hoping for a culprit.

> Evidence `tr_37bb607ee689`:

```
<tool_result id="tr_37bb607ee689" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-15T08:15:15.583000+00:00..2026-09-15T08:47:17.539629+00:00" template="error-ratio" baseline="2026-09-15T07:43:13.626371+00:00..2026-09-15T08:15:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=129 mean=0.05219 min=0 max=0.3038 sd=0.08424
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

## Narrowing to checkoutservice

checkoutservice showed the same shape one layer down: flat zero across the entire baseline, then a single abrupt change point with the error ratio crossing threshold at around 12.8% and peaking near 67%. The incident-window minimum stayed at zero and the spread exceeded the mean, so failures were bursty — some orders went through, some died instantly.

The logs were the first genuinely useful narrowing step, and also the first surprise. Early in the window each order emitted a tidy four-line sequence: order start, payment confirmation with a transaction id, confirmation email, then a successful message write with an offset. From roughly the onset onward, only the order-start lines survive. Payment, email and the write completion vanish. Orders were being accepted but not finishing.

Crucially, the stream contained no error or warning severity lines at all, no dependency name, no deadline or context-cancellation text, no resource-limit message. The order-start cadence held steady at one every five to fifteen seconds right to the end of the window, so checkoutservice was neither wedged nor restarting in a loop. Both USD and CAD orders appeared among the stalled ones, so nothing currency-scoped.

> Evidence `tr_f0db5295bd36`:

```
<tool_result id="tr_f0db5295bd36" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-15T08:15:15.583000+00:00..2026-09-15T08:47:17.539629+00:00" template="error-ratio" baseline="2026-09-15T07:43:13.626371+00:00..2026-09-15T08:15:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.0727 min=0 max=0.6667 sd=0.2032
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_73a8955b0079`:

```
<tool_result id="tr_73a8955b0079" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-15T08:15:15.583000+00:00..2026-09-15T08:47:17.539629+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-15T08:15:30.059319+00:00  {"message":"[PlaceOrder] user_id=\"9d667d2a-b0dd-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-15T08:15:30.059202833Z"}
2026-09-15T08:15:30.079500+00:00  {"message":"payment went through (transaction_id: eb5241ed-9c3e-4a39-be69-9f8f74dae8b4)","severity":"info","timestamp":"2026-09-15T08:15:30.079387875Z"}
2026-09-15T08:15:30.085211+00:00  {"message":"order confirmation email sent to \"bill@example.com\"","severity":"info","timestamp":"2026-09-15T08:15:30.085108625Z"}
2026-09-15T08:15:30.087830+00:00  {"message":"Successful to write message. offset: 58747","severity":"info","timestamp":"2026-09-15T08:15:30.087763666Z"}
```

## The traces settle it

Trace sampling is what resolved the record. Every failing PlaceOrder trace aborts in the same place: inside prepareOrderItemsAndShippingQuoteFromCart, on checkoutservice's outbound client span for CartService/GetCart. That span carries an error status, and the status propagates up through checkoutservice, through frontend's PlaceOrder, and out to the frontend HTTP root — which is exactly the chain that produced the original alerts.

Two properties of those failing spans shaped the conclusion. First, there is no cartservice server-side child span; failing traces are five spans and stop at the client span. The call never produced a recorded server-side handler at all. Second, they are fast: the erroring span runs two to four milliseconds and the whole trace ends in three to six, against roughly twenty-six to thirty for a healthy checkout. That is far too fast for any RPC deadline. The signature is an immediate connection-level rejection.

checkoutservice is the reporter, not the source. Its own self-time in failing traces is about a tenth to two tenths of a millisecond. Traces sampled earlier in the window are complete and successful, including a healthy GetCart with an HGET child, which brackets onset of the cart failure to a span of roughly four minutes inside the window.

> Evidence `tr_f6db098f108b`:

```
<tool_result id="tr_f6db098f108b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-15T07:45:15.583000+00:00..2026-09-15T08:47:17.539629+00:00">
service: checkoutservice
11 trace(s) shown of 35 found, 200 spans; offsets are from each trace's root

trace 86437b031f5c2dc4  root frontend/HTTP POST  57.2ms  started 2026-09-15T08:39:29.475018+00:00  36 spans
  +0.0ms frontend/HTTP POST 57.2ms [self 0.6ms]
```

## Dead ends, and why they were dead

Keep these; they are most of the value of this record.

Every downstream of checkout that looked suspicious on the log evidence was cleared by traces, and for the same structural reason: the trace aborts at GetCart, so those hops are never attempted. Their absence is a consequence, not a second failure. paymentservice Charge completes in about one and a half milliseconds with a clean server span in every healthy trace. emailservice send_email completes cleanly — though in one healthy trace it accounted for around thirty milliseconds, over half the trace self-time, which is a latency contributor and nothing more. currencyservice Convert is sub-two-millisecond and clean. shippingservice GetQuote/ShipOrder is the slowest non-email hop at seven to ten milliseconds but never errors. productcatalogservice succeeds both from checkout and from frontend.

The paymentservice metrics detour is worth flagging as a trap. The error-ratio query returned nothing — no samples in the incident window and none in the hour of baseline before it. The correct reading is that these call metrics were never being emitted under that label set, not that payment went dark at onset. Empty is not healthy and empty is not a crash signal; do not clear or accuse a service on that basis. Latency was never evaluated for payment at all.

Change history was queried three times and came back empty every time: checkoutservice, productcatalogservice, paymentservice. That rules out deploy, config push, flag flip, flapping rollout and quiet rollback on those three, and it also rules out rollback as a remediation — there is nothing to roll back to. But note two scope limits. The checkoutservice change query covered only the seed service at zero hops and, worse, its window began *at* onset and ran forward roughly twenty-four hours, so it never examined the minutes immediately before. The productcatalogservice query likewise excluded cartservice and adservice.

> Evidence `tr_f6db098f108b`:

```
<tool_result id="tr_f6db098f108b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-15T07:45:15.583000+00:00..2026-09-15T08:47:17.539629+00:00">
service: checkoutservice
11 trace(s) shown of 35 found, 200 spans; offsets are from each trace's root

trace 86437b031f5c2dc4  root frontend/HTTP POST  57.2ms  started 2026-09-15T08:39:29.475018+00:00  36 spans
  +0.0ms frontend/HTTP POST 57.2ms [self 0.6ms]
```

> Evidence `tr_802990ccc0e7`:

```
<tool_result id="tr_802990ccc0e7" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-15T07:45:15.583000+00:00..2026-09-15T08:47:17.539629+00:00" template="error-ratio" baseline="2026-09-15T06:43:13.626371+00:00..2026-09-15T07:45:15.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_dd2c91695fac`:

```
<tool_result id="tr_dd2c91695fac" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-14T08:45:15.583000+00:00..2026-09-15T08:47:17.539629+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_dd2c91695fac>
```

> Evidence `tr_14e3bcb658a7`:

```
<tool_result id="tr_14e3bcb658a7" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-14T08:45:15.583000+00:00..2026-09-15T08:47:17.539629+00:00" radius="candidate_cause" hops="1">
no changes recorded for productcatalogservice over this window
</tool_result:tr_14e3bcb658a7>
```

> Evidence `tr_77c6798f30ef`:

```
<tool_result id="tr_77c6798f30ef" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-14T08:45:15.583000+00:00..2026-09-15T08:47:17.539629+00:00" radius="candidate_cause" hops="1">
no changes recorded for paymentservice over this window
</tool_result:tr_77c6798f30ef>
```

## Where it landed, and what is still open

Conclusion, held at medium confidence: the checkout errors visible at frontend originate on the checkoutservice → cartservice edge, as an immediate connection-level refusal of GetCart. Indicated remediation class is a restart of the cart tier.

The confidence is medium and not high for one blunt reason: cartservice was never dispatched. Its metrics, logs, restart and OOM counts and change history are wholly unexamined, and the mechanism lives there. We know the call is refused; we do not know why no server span appears — process gone, connections rejected at a listener or pool limit, endpoint misresolved, or a bad artifact. Anyone picking this up should start there, and should also pull cartservice change history over the window *preceding* onset, which no query in this record covered.

Second loose thread: frontend's error ratio crossed threshold roughly twelve minutes before the cart failure onset bracket, with a second crossing closer to it. checkoutservice, by contrast, shows a single change point inside that bracket. The cart edge cannot explain the earlier frontend rise, so either an earlier contributor or a second one is unaccounted for. Four edges in the blast radius were crossed without direct measurement, and the investigation was called before that gap closed.

> Evidence `tr_f6db098f108b`:

```
<tool_result id="tr_f6db098f108b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-15T07:45:15.583000+00:00..2026-09-15T08:47:17.539629+00:00">
service: checkoutservice
11 trace(s) shown of 35 found, 200 spans; offsets are from each trace's root

trace 86437b031f5c2dc4  root frontend/HTTP POST  57.2ms  started 2026-09-15T08:39:29.475018+00:00  36 spans
  +0.0ms frontend/HTTP POST 57.2ms [self 0.6ms]
```

> Evidence `tr_37bb607ee689`:

```
<tool_result id="tr_37bb607ee689" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-15T08:15:15.583000+00:00..2026-09-15T08:47:17.539629+00:00" template="error-ratio" baseline="2026-09-15T07:43:13.626371+00:00..2026-09-15T08:15:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=129 mean=0.05219 min=0 max=0.3038 sd=0.08424
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_f0db5295bd36`:

```
<tool_result id="tr_f0db5295bd36" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-15T08:15:15.583000+00:00..2026-09-15T08:47:17.539629+00:00" template="error-ratio" baseline="2026-09-15T07:43:13.626371+00:00..2026-09-15T08:15:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.0727 min=0 max=0.6667 sd=0.2032
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

