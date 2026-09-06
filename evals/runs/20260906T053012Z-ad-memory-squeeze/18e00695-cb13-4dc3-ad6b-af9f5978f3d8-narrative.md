# Frontend partial errors traced to an unreachable ad dependency

## What the page looked like

Two alerts arrived together: frontend and loadgenerator. Nothing else in the seven-service blast radius paged. The first thing I pulled was frontend's own error ratio across the incident window, and it came back around 6.7% on average, ranging roughly 1.8% to 8.9% over twenty samples, with every single sample non-zero. That shape mattered more than the number: continuous, partial, never anywhere near saturation. A service that is wholly broken does not sit at 7% for an hour, and a transient blip does not appear in all twenty buckets.

One trap here that I want on the record. The tool compared against the preceding hour and announced 'no sustained departure from baseline.' That verdict is worthless in this case — the baseline hour returned zero samples, so the comparison had nothing to compare against. If you read that line and stop, you clear a service that is actively erroring. Do not.

> Evidence `tr_c2c0ad8cea56`:

```
<tool_result id="tr_c2c0ad8cea56" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-06T04:33:45.583000+00:00..2026-09-06T05:35:31.301938+00:00" template="error-ratio" baseline="2026-09-06T03:31:59.864062+00:00..2026-09-06T04:33:45.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=20 mean=0.06683 min=0.01764 max=0.08912 sd=0.01937
  baseline window: no samples
```

## Narrowing to a single edge

The error-ratio query aggregated only by service name; it carried no downstream dimension and no latency at all, so it could not tell me which dependency was involved. Traces did. In the sampled window, every errored outbound span from frontend sat on the same edge: the GetAds call to adservice. Three such spans appeared across three separate traces, and all three were marked ERROR. The calls hung roughly 1.8 to 3.1 seconds before failing, and in at least one trace the error attached to a connect-phase child span underneath the gRPC call rather than to the call itself.

The decisive negative: no adservice server-side span appeared anywhere in the sample. Nothing on the callee side ever answered. Frontend's slow HTTP entry spans were slow purely because they inherited the ad-fetch child's duration; the same frontend served plenty of other requests in the same window at 1–70ms cleanly. Its other outbound edges — product catalog, cart, recommendation, checkout — all completed sub-10ms and unmarked. A full PlaceOrder trace ran end to end with payment, shipping quote, currency conversion and email all present and healthy. Cart's Redis operations finished in well under a millisecond.

This is what reconciles the 7%: one non-critical-path dependency unreachable, everything else fine.

> Evidence `tr_9a634247001e`:

```
<tool_result id="tr_9a634247001e" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-06T04:03:45.583000+00:00..2026-09-06T05:35:31.301938+00:00">
service: frontend
200 spans
  e59b45fd980f2821 cartservice/HMSET 0.2ms
  e59b45fd980f2821 cartservice/hipstershop.CartService/GetCart 0.4ms
  e59b45fd980f2821 cartservice/HGET 0.2ms
```

> Evidence `tr_c2c0ad8cea56`:

```
<tool_result id="tr_c2c0ad8cea56" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-06T04:33:45.583000+00:00..2026-09-06T05:35:31.301938+00:00" template="error-ratio" baseline="2026-09-06T03:31:59.864062+00:00..2026-09-06T04:33:45.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=20 mean=0.06683 min=0.01764 max=0.08912 sd=0.01937
  baseline window: no samples
```

## What the logs confirmed and what they refused to say

Frontend's logs carried exactly one error signature: gRPC status 14 UNAVAILABLE, with the detail string saying no connection was established, and empty gRPC metadata. The stack frames were entirely inside the @grpc/grpc-js client library, reached via the async task queue — raised client-side when a call status is received, not from frontend's own handler code. Empty metadata plus that detail means the call died before any server response existed. This rules out the interpretations that would have sent me elsewhere: it is not an HTTP 5xx from a REST backend, not DEADLINE_EXCEEDED or RESOURCE_EXHAUSTED or INTERNAL from an overloaded-but-live handler, and not a callee that accepted the connection and then failed mid-processing.

The logs also refused to name the target. No host, no port, no service name, no method appears in any line. If you come to this incident expecting frontend's logs to identify the unreachable dependency, you will waste time; that identification came from traces only.

On timing: a single frontend process start appears around 22 minutes before the earliest error line returned, and the newest lines through the end of the window show no further startup banners or exits — frontend stayed up throughout. But the log result was truncated to the oldest 8 and newest 32 lines, so the earliest error timestamp I have is an upper bound on onset, not a confirmed first occurrence. Errors may well exist in the unreturned middle.

> Evidence `tr_50ac94ec3a65`:

```
<tool_result id="tr_50ac94ec3a65" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T04:33:45.583000+00:00..2026-09-06T05:35:31.301938+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-06T05:08:06.035610+00:00  
2026-09-06T05:08:06.035636+00:00  > frontend@0.1.0 start
2026-09-06T05:08:06.035638+00:00  > node --require ./Instrumentation.js server.js
2026-09-06T05:08:06.035639+00:00  
```

## Dead ends worth keeping

Change history on frontend returned absolutely nothing for the whole window — no deploys, no config edits, no flag flips, no dependency-endpoint repointing, no rollbacks. That closes the entire family of 'someone shipped something to frontend' hypotheses, but note the scope limit: the query covered the seed service only, zero hops, so adservice and the other four were never examined this way.

Product catalog's change history was likewise empty across a full 24 hours. Nothing to roll back there either.

Cartservice was the most seductive dead end. It had 18 recorded changes in the window, all by a single actor, platform-automation, in repeated apply-then-revert pairs: an image reference set to a hotfix tag and reverted several times, a Redis address environment variable pointed at a non-default port and reverted twice, and a traffic-shaping sidecar attached to the cart network namespace to add fixed egress delay, then removed, twice. It reads like automated experiment cycling rather than human release work. But every single mutation has a matching revert, and the latest of them completed about 2.6 hours before onset — cartservice was back at baseline image, environment and network configuration when the incident started. Nothing is recorded at or after onset. I spent time here and it did not pay.

The metrics budget was largely wasted. Error-ratio queries against cartservice, productcatalogservice and recommendationservice all returned zero samples — and critically, zero samples in the baseline hour too. Equally empty on both sides means the series simply is not populated for those service labels, an instrumentation gap that predates the incident. Do not read those empties as health, and do not read them as a service going silent at onset. Each of those three queries also only ran the error-ratio template; inbound request rate, restart counts and target availability were never measured for any of them.

> Evidence `tr_2ec6e72b8156`:

```
<tool_result id="tr_2ec6e72b8156" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-05T05:33:45.583000+00:00..2026-09-06T05:35:31.301938+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_2ec6e72b8156>
```

> Evidence `tr_f3426b55bbce`:

```
<tool_result id="tr_f3426b55bbce" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-05T05:33:45.583000+00:00..2026-09-06T05:35:31.301938+00:00" radius="candidate_cause" hops="1">
no changes recorded for productcatalogservice over this window
</tool_result:tr_f3426b55bbce>
```

> Evidence `tr_a81fea393463`:

```
<tool_result id="tr_a81fea393463" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-05T05:33:45.583000+00:00..2026-09-06T05:35:31.301938+00:00" radius="candidate_cause" hops="1">
service: cartservice
18 changes, ranked by suspicion
  #1  2.6h before onset  2026-09-06T02:57:35.534360+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  2.7h before onset  2026-09-06T02:49:11.096731+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

> Evidence `tr_f2e14992f758`:

```
<tool_result id="tr_f2e14992f758" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-06T03:33:45.583000+00:00..2026-09-06T05:35:31.301938+00:00" template="error-ratio" baseline="2026-09-06T01:31:59.864062+00:00..2026-09-06T03:33:45.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_242f22d5bca1`:

```
<tool_result id="tr_242f22d5bca1" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-06T03:33:45.583000+00:00..2026-09-06T05:35:31.301938+00:00" template="error-ratio" baseline="2026-09-06T01:31:59.864062+00:00..2026-09-06T03:33:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_269aad10749b`:

```
<tool_result id="tr_269aad10749b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-06T03:33:45.583000+00:00..2026-09-06T05:35:31.301938+00:00" template="error-ratio" baseline="2026-09-06T01:31:59.864062+00:00..2026-09-06T03:33:45.583000+00:00">
service: recommendationservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="recommendationservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="recommendationservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Where I stopped

The conclusion I am comfortable with: adservice is not accepting connections at its advertised endpoint, and frontend's partial error rate is the direct consequence. Service named with confidence.

The mechanism I will not name. No adservice-scoped work was ever dispatched — no logs, no change history, no restart counts, no target availability from that service. Process down, crash-loop, out-of-memory kill, or a listener bound to the wrong address would all produce exactly the evidence above, and I have nothing that separates them. Confidence medium; likely fix class is a restart, but that is inference from the failure shape rather than from anything measured on the failing service.

> Evidence `tr_9a634247001e`:

```
<tool_result id="tr_9a634247001e" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-06T04:03:45.583000+00:00..2026-09-06T05:35:31.301938+00:00">
service: frontend
200 spans
  e59b45fd980f2821 cartservice/HMSET 0.2ms
  e59b45fd980f2821 cartservice/hipstershop.CartService/GetCart 0.4ms
  e59b45fd980f2821 cartservice/HGET 0.2ms
```

> Evidence `tr_50ac94ec3a65`:

```
<tool_result id="tr_50ac94ec3a65" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T04:33:45.583000+00:00..2026-09-06T05:35:31.301938+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-06T05:08:06.035610+00:00  
2026-09-06T05:08:06.035636+00:00  > frontend@0.1.0 start
2026-09-06T05:08:06.035638+00:00  > node --require ./Instrumentation.js server.js
2026-09-06T05:08:06.035639+00:00  
```

## Still open for whoever picks this up

First and largest: adservice was never queried at all. That is the obvious first move on any recurrence — its logs, its restart count, its target availability, its change history.

Second: the platform-automation cycling observed on cartservice raises the question of whether similar automated apply/revert activity was aimed at adservice and left unreverted. Nobody checked. If it was, both the classification and the remediation change — you would revert rather than restart.

Third: onset is not pinned. The log truncation makes the earliest observed error an upper bound only, and the 3-of-3 edge failure rate comes from a 200-span truncated sample, which is a sample statistic, not a window-wide fraction. The underlying status code value was not present in the returned span text either; the code 14 attribution comes from the logs, correlated by shape rather than by a shared identifier.

> Evidence `tr_a81fea393463`:

```
<tool_result id="tr_a81fea393463" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-05T05:33:45.583000+00:00..2026-09-06T05:35:31.301938+00:00" radius="candidate_cause" hops="1">
service: cartservice
18 changes, ranked by suspicion
  #1  2.6h before onset  2026-09-06T02:57:35.534360+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  2.7h before onset  2026-09-06T02:49:11.096731+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

> Evidence `tr_50ac94ec3a65`:

```
<tool_result id="tr_50ac94ec3a65" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T04:33:45.583000+00:00..2026-09-06T05:35:31.301938+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-06T05:08:06.035610+00:00  
2026-09-06T05:08:06.035636+00:00  > frontend@0.1.0 start
2026-09-06T05:08:06.035638+00:00  > node --require ./Instrumentation.js server.js
2026-09-06T05:08:06.035639+00:00  
```

> Evidence `tr_9a634247001e`:

```
<tool_result id="tr_9a634247001e" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-06T04:03:45.583000+00:00..2026-09-06T05:35:31.301938+00:00">
service: frontend
200 spans
  e59b45fd980f2821 cartservice/HMSET 0.2ms
  e59b45fd980f2821 cartservice/hipstershop.CartService/GetCart 0.4ms
  e59b45fd980f2821 cartservice/HGET 0.2ms
```

