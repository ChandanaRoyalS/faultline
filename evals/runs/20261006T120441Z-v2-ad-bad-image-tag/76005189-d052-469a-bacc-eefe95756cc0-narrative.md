# Frontend gRPC calls failing against one unreachable upstream address

## What we saw first

The page came from frontend and frontend-proxy. The first thing on screen was frontend's error ratio: a mean of roughly 3.4% of calls erroring during the window against a baseline near 0.47%, about seven times normal, peaking around 8.4% — roughly one call in twelve failing at the worst moment. Two things about that curve mattered more than the headline number. First, it was not a blip at alert time: the ratio crossed the anomaly threshold at T+0, with further shifts at T+2m and T+28m, so the condition had been running about half an hour before anyone was paged at T+30m. Second, the query behind it aggregates only by service name. It tells you frontend is erroring and nothing at all about which downstream is responsible — worth remembering, because the next half hour was spent trying to recover that missing dimension from other sources.

> Evidence `tr_472153e4ed14`:

```
<tool_result id="tr_472153e4ed14" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T11:39:31.664000+00:00..2026-10-06T12:11:22.174947+00:00" template="error-ratio" baseline="2026-10-06T11:07:41.153053+00:00..2026-10-06T11:39:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0.03402 min=0 max=0.08397 sd=0.03201
  baseline window: n=128 mean=0.004728 min=0 max=0.05974 sd=0.01403
```

## The trace detour (this is the dead end)

The obvious next move was traces from frontend, and the obvious next move produced a confident, wrong-shaped answer. Ten slow traces came back. None of them carried an explicit error or timeout status on any span. What they did show was depth: product-reviews spans sat lowest in the call tree and absorbed the most elapsed time — get_ai_assistant_response at 74% of trace time in two AI-assistant traces, get_product_reviews at 42–66% in two review traces, with leaf SELECT and POST spans five or six levels below the frontend root. ad, cart and product-catalog appeared too but shallower and with most of the elapsed time attributable to load-generator self-time. Checkout and recommendation never appeared at all.

So the trace view pointed squarely at product-reviews, and we chased it. That cost time. The tell, visible in hindsight, is that the traces contained no errors — they were a slowness picture, while the alert was an error-ratio picture. Sampled traces that complete successfully cannot show you calls that never get a connection.

> Evidence `tr_751b4dbe028b`:

```
<tool_result id="tr_751b4dbe028b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-06T11:39:31.664000+00:00..2026-10-06T12:11:22.174947+00:00">
service: frontend
10 trace(s) shown of 10 found, 120 spans; offsets are from each trace's root

trace a289706763815c37  root load-generator/user_browse_product  5.4ms  started 2026-10-06T11:58:17.622393+00:00  10 spans
  +0.0ms load-generator/user_browse_product 5.4ms [self 0.5ms]
```

## Clearing product-reviews

Two checks closed the detour. Product-reviews' own error ratio over the same window averaged 0.0018 against a baseline of 0.0016 — a 1.12x difference, maxima comparable, no sustained departure from baseline. Its logs across the window were INFO only: no error or warning lines, every call to the upstream LLM endpoint returning 200, and the two behaviour toggles it logs (llmRateLimitError, llmInaccurateResponse) both recorded as False. Product-reviews was slow in traces but it was not failing, and it was not the thing frontend was erroring on.

One loose end survives from this: the 30-minute-wide trace-level slowness in get_ai_assistant_response is still unexplained. It overlaps the incident but nothing links it causally. Treat it as a possible separate concern, not a consequence.

> Evidence `tr_b97307137d0b`:

```
<tool_result id="tr_b97307137d0b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T11:39:31.664000+00:00..2026-10-06T12:11:22.174947+00:00" template="error-ratio" baseline="2026-10-06T11:07:41.153053+00:00..2026-10-06T11:39:31.664000+00:00">
service: product-reviews
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-reviews",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="product-reviews"}[5m]))
  incident window: n=128 mean=0.001779 min=0 max=0.005682 sd=0.002322
  baseline window: n=128 mean=0.001583 min=0 max=0.005155 sd=0.002067
```

> Evidence `tr_909348d8809d`:

```
<tool_result id="tr_909348d8809d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T11:39:31.664000+00:00..2026-10-06T12:11:22.174947+00:00" oldest_kept="8" newest_kept="32">
selector: {service="product-reviews"}
2026-10-06T11:39:42.955349+00:00  2026-10-06 11:39:42,954 INFO [main] [product_reviews_server.py:92] [trace_id=3f581f9533ef241c03bd5625b1853dce span_id=a1db34eeb00373ce resource.service.name=product-reviews trace_sampled=True] - Receive GetProductReviews for product id:L9ECAV7KIM
2026-10-06T11:39:42.968131+00:00  2026-10-06 11:39:42,967 INFO [main] [product_reviews_server.py:127] [trace_id=3f581f9533ef241c03bd5625b1853dce span_id=38475a3fd673a279 resource.service.name=product-reviews trace_sampled=True] -   username: clean_optics, description: This kit is a lifesaver for all my optics. The brush and wipes work perfectly without leaving any residue. My lenses have never been cleaner., score: 5.0
2026-10-06T11:39:42.968508+00:00  2026-10-06 11:39:42,968 INFO [main] [product_reviews_server.py:127] [trace_id=3f581f9533ef241c03bd5625b1853dce span_id=38475a3fd673a279 resource.service.name=product-reviews trace_sampled=True] -   username: photog_pro, description: Essential for any photographer or telescope owner. It safely removes dust and fingerprints. A high-quality cleaning solution., score: 4.5
2026-10-06T11:39:42.968600+00:00  2026-10-06 11:39:42,968 INFO [main] [product_reviews_server.py:127] [trace_id=3f581f9533ef241c03bd5625b1853dce span_id=38475a3fd673a279 resource.service.name=product-reviews trace_sampled=True] -   username: daily_cleaner, description: I use this on my binoculars, camera lenses, and even my phone screen. It's very effective and gentle. A versatile cleaning kit., score: 4.0
```

## What the logs actually said

Frontend's own log lines were where the answer had been sitting the whole time. Every error in the window was gRPC status 14 UNAVAILABLE, and every one named the same single target: 172.18.0.19 on port 9555. The underlying socket error was EHOSTUNREACH. That distinction carries the whole conclusion — no-route-to-host is not a refused connection and not a timeout, so this is lost reachability to an address rather than an overloaded or misbehaving peer. The lines run continuously from T+0m through T+32m, and a connection attempt stamped at T+30m lands exactly on the alert time. Nothing application-level appears: no 4xx/5xx, no auth failures, no business exceptions. No other host or port is ever named.

> Evidence `tr_2fb5ffc9c7e7`:

```
<tool_result id="tr_2fb5ffc9c7e7" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T11:39:31.664000+00:00..2026-10-06T12:11:22.174947+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-06T11:39:33.621053+00:00  Error: 14 UNAVAILABLE: No connection established. Last error: connect EHOSTUNREACH 172.18.0.19:9555 (2026-10-06T11:38:21.153Z)
2026-10-06T11:39:33.621086+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__3ea42e2a._.js:1:531)
2026-10-06T11:39:33.621089+00:00      at new Promise (<anonymous>) {
2026-10-06T11:39:33.621089+00:00    code: 14,
```

## Change history

Checked deploys, config edits and toggle flips for frontend and every downstream candidate (ad, cart, checkout, product-catalog, product-reviews, recommendation) across the preceding 24 hours. The window was queried and came back empty. That is a real result, not a gap: a connectivity loss with no accompanying change is consistent with the EHOSTUNREACH picture and argues against anything that shipped.

> Evidence `tr_02526dd4aae4`:

```
<tool_result id="tr_02526dd4aae4" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T12:09:31.664000+00:00..2026-10-06T12:11:22.174947+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_02526dd4aae4>
```

## Conclusion and confidence

Frontend is failing roughly 3.4% of calls, peaking near 8.4%, because one gRPC upstream at 172.18.0.19:9555 is unreachable at the network layer. Frontend is not isolated generally — its other downstreams answer normally inside the same traces — only this one peer is gone. Fix class is reconnect: restore routing to that endpoint or get the peer rescheduled onto a routable address.

Confidence is medium, and the reason is attribution. No evidence in this record resolves 172.18.0.19:9555 to a named service. We call it the ad service because 9555 is its conventional gRPC port in this deployment and because ad spans show up in the traces. That is inference, not confirmation.

> Evidence `tr_2fb5ffc9c7e7`:

```
<tool_result id="tr_2fb5ffc9c7e7" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T11:39:31.664000+00:00..2026-10-06T12:11:22.174947+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-06T11:39:33.621053+00:00  Error: 14 UNAVAILABLE: No connection established. Last error: connect EHOSTUNREACH 172.18.0.19:9555 (2026-10-06T11:38:21.153Z)
2026-10-06T11:39:33.621086+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__3ea42e2a._.js:1:531)
2026-10-06T11:39:33.621089+00:00      at new Promise (<anonymous>) {
2026-10-06T11:39:33.621089+00:00    code: 14,
```

> Evidence `tr_751b4dbe028b`:

```
<tool_result id="tr_751b4dbe028b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-06T11:39:31.664000+00:00..2026-10-06T12:11:22.174947+00:00">
service: frontend
10 trace(s) shown of 10 found, 120 spans; offsets are from each trace's root

trace a289706763815c37  root load-generator/user_browse_product  5.4ms  started 2026-10-06T11:58:17.622393+00:00  10 spans
  +0.0ms load-generator/user_browse_product 5.4ms [self 0.5ms]
```

> Evidence `tr_472153e4ed14`:

```
<tool_result id="tr_472153e4ed14" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T11:39:31.664000+00:00..2026-10-06T12:11:22.174947+00:00" template="error-ratio" baseline="2026-10-06T11:07:41.153053+00:00..2026-10-06T11:39:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0.03402 min=0 max=0.08397 sd=0.03201
  baseline window: n=128 mean=0.004728 min=0 max=0.05974 sd=0.01403
```

## Open for the next responder

Three things were not closed. One: map 172.18.0.19:9555 to a service by name — service discovery records or the pod's address history would do it in a minute and would raise confidence from medium to high. Two: nobody looked at ad directly. Its own logs settle the shape of the failure immediately — a process that is up and complaining about lost peers means a connectivity break, while silence plus an address that no longer routes means the pod crashed or was descheduled. Those want different fixes. Three: the product-reviews slowness described above remains unexplained and should be picked up separately rather than written off as collateral.

> Evidence `tr_2fb5ffc9c7e7`:

```
<tool_result id="tr_2fb5ffc9c7e7" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T11:39:31.664000+00:00..2026-10-06T12:11:22.174947+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-06T11:39:33.621053+00:00  Error: 14 UNAVAILABLE: No connection established. Last error: connect EHOSTUNREACH 172.18.0.19:9555 (2026-10-06T11:38:21.153Z)
2026-10-06T11:39:33.621086+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__3ea42e2a._.js:1:531)
2026-10-06T11:39:33.621089+00:00      at new Promise (<anonymous>) {
2026-10-06T11:39:33.621089+00:00    code: 14,
```

> Evidence `tr_751b4dbe028b`:

```
<tool_result id="tr_751b4dbe028b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-06T11:39:31.664000+00:00..2026-10-06T12:11:22.174947+00:00">
service: frontend
10 trace(s) shown of 10 found, 120 spans; offsets are from each trace's root

trace a289706763815c37  root load-generator/user_browse_product  5.4ms  started 2026-10-06T11:58:17.622393+00:00  10 spans
  +0.0ms load-generator/user_browse_product 5.4ms [self 0.5ms]
```

