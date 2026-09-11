# Critical: catalog dependency returning INTERNAL to frontend callers

## What we saw first

Paging came from three places at once: frontend, loadgenerator, and productcatalogservice. Triage put seven services in the blast radius and marked the walk as starting at frontend, with one edge crossed that we never actually measured. Treat T+0 as the alert reference point the pagers carried; everything below is relative to it.

The first honest picture came from frontend's own error ratio, and it was misleading. Over the half hour ending at T+2m, frontend averaged roughly 1.3% errors with a peak near 11% — about a quarter of the preceding baseline, which had averaged around 5.4% with peaks near 30%. The tooling reported no sustained departure from baseline. If you arrive at this record expecting the customer-facing service to look broken, it did not. A responder reading only that panel would reasonably have closed the page. That measurement is also service-level only, with no per-dependency breakdown, so it could neither accuse nor clear any downstream.

> Evidence `tr_1ebf001ca2cc`:

```
<tool_result id="tr_1ebf001ca2cc" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T06:36:45.583000+00:00..2026-09-10T07:08:49.114959+00:00" template="error-ratio" baseline="2026-09-10T06:04:42.051041+00:00..2026-09-10T06:36:45.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=129 mean=0.01347 min=0 max=0.1081 sd=0.03237
  baseline window: n=129 mean=0.05372 min=0 max=0.3013 sd=0.1059
```

## The signal that actually moved

productcatalogservice's error ratio was the clean one. Across a three-hour baseline it was flat at exactly zero — 440 samples, min, max, mean and standard deviation all zero. There was no error floor to worsen. Then a single change point: the ratio crossed 5% at T-105s and peaked near 11%.

Two things follow from that shape. First, this is a discrete zero-to-nonzero transition, not a proportional climb, so the slow-degradation stories (a leak, gradual pressure on the process) do not fit; only one change point was detected across 729 incident-window samples, so intermittent flapping does not fit either. Second, the crossing precedes the alert reference by about a minute and three quarters. The catalog errors lead the marker rather than follow it, which removes the reading in which the catalog is a downstream casualty of whatever the alert was about.

The important caveat: latency, CPU and memory for this service were requested and never returned. Three of four signals are unmeasured, so a resource-driven contribution is unexcluded rather than excluded.

> Evidence `tr_45c62bb85445`:

```
<tool_result id="tr_45c62bb85445" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T04:06:45.583000+00:00..2026-09-10T07:08:49.114959+00:00" template="error-ratio" baseline="2026-09-10T01:04:42.051041+00:00..2026-09-10T04:06:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=729 mean=0.002313 min=0 max=0.1099 sd=0.01484
  baseline window: n=440 mean=0 min=0 max=0 sd=0
```

## The frontend logs, and what they name

The tail of the frontend log window is where the answer sits. Around T+2m, frontend emits repeated gRPC client errors carrying status 13 INTERNAL, and the details string on those errors names a product-catalog failure feature flag being in an enabled state. The stack frames are grpc-js client interceptor and call-status frames — that is, frontend receiving a status from a callee, not throwing from its own handler. The error text is callee-supplied. That distinction is what lets us say the failure is generated inside productcatalogservice and merely surfaced at frontend.

The same lines let us clear two neighbours: no adservice-named and no cartservice-named failures appear anywhere in the returned window. Only the catalog dependency is named.

> Evidence `tr_43523bfab685`:

```
<tool_result id="tr_43523bfab685" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T06:36:45.583000+00:00..2026-09-10T07:08:49.114959+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T06:41:59.276453+00:00  Error: 13 INTERNAL: failed to charge card: could not charge the card: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.15:50051: connect: connection refused"
2026-09-10T06:41:59.276489+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T06:41:59.276491+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T06:41:59.276492+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Dead end: the early connection-refused errors

About twenty-five minutes before the alert reference, frontend logged a different failure entirely — a code 13 INTERNAL on the card-charge path wrapping an Unavailable transport dial error, connection refused against a peer address on port 50051. It is tempting to fold this into the main story, and we spent time trying to. It does not fold.

The error signature changes across the window: transport-level refusal early, application-level INTERNAL with a flag-named details string late. Different call path, different failure class, different time. We never attributed the 50051 refusal to a named service; it remains an open thread and, on the evidence, a separate problem. Flag it if it recurs, but do not let it anchor the timeline.

> Evidence `tr_43523bfab685`:

```
<tool_result id="tr_43523bfab685" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T06:36:45.583000+00:00..2026-09-10T07:08:49.114959+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T06:41:59.276453+00:00  Error: 13 INTERNAL: failed to charge card: could not charge the card: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.15:50051: connect: connection refused"
2026-09-10T06:41:59.276489+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T06:41:59.276491+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T06:41:59.276492+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Dead end: the change log

The obvious next move was to find the moment the flag flipped. We queried change history for productcatalogservice twice, and got nothing both times — no deploys, no config edits, no flag toggles.

The emptiness is real but nearly useless, because both queries were windowed from the alert reference forward roughly twenty-four hours. They cover the incident and the day after it, not the hours before. So what they legitimately rule out is narrow: no deploy coincided with or followed onset, no undocumented mitigation landed during the window, nothing was left in place and un-reverted afterward, and the service was static for the following day. What they cannot address is the question we asked. The pre-onset hours where an enable would appear were never queried. A responder repeating this should set the window to start hours before onset.

> Evidence `tr_9eb4b888ea57`:

```
<tool_result id="tr_9eb4b888ea57" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T07:06:45.583000+00:00..2026-09-10T07:08:49.114959+00:00" radius="seed" hops="0">
no changes recorded for productcatalogservice over this window
</tool_result:tr_9eb4b888ea57>
```

> Evidence `tr_fb55115e9618`:

```
<tool_result id="tr_fb55115e9618" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T07:06:45.583000+00:00..2026-09-10T07:08:49.114959+00:00" radius="seed" hops="0">
no changes recorded for productcatalogservice over this window
</tool_result:tr_fb55115e9618>
```

## Dead end: the callee's own logs

We tried to read productcatalogservice's logs directly to confirm the flag from the callee side. The selector `{service="product-catalog-service"}` returned zero lines over the whole two-hour window — not zero errors, zero output, including ordinary startup and request-handling chatter.

A service handling traffic and emitting nothing at all is far more likely a label mismatch than genuine silence; the compact, unhyphenated form is the first thing to try. Because of that, this query supports nothing and refutes nothing about the callee's error text. It does establish that no loud indexed error stream exists under this particular selector, and that no log-volume spike is observable there, but that is a statement about the selector, not the process.

> Evidence `tr_2f2afdbbe325`:

```
<tool_result id="tr_2f2afdbbe325" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-09-10T05:06:45.583000+00:00..2026-09-10T07:08:49.114959+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_2f2afdbbe325>
```

## Conclusion and fix class

productcatalogservice began returning gRPC status 13 INTERNAL to its callers because a product-catalog failure feature flag was in an enabled state. Two independent lines meet here: the callee-supplied details string naming that flag in frontend's client-side status frames, and the catalog's own discrete zero-to-nonzero error transition leading the alert reference by roughly 105 seconds.

The failing mechanism is a configuration value that is itself wrong — the flag's enabled state is what makes the request fail. So the fix class is a config revert: turn the flag off. Restarting, rolling back a build, or scaling the service would not address it, because nothing was deployed and nothing is saturated as far as we measured.

Confidence is medium, not high, and the reasons are listed below.

> Evidence `tr_43523bfab685`:

```
<tool_result id="tr_43523bfab685" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T06:36:45.583000+00:00..2026-09-10T07:08:49.114959+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T06:41:59.276453+00:00  Error: 13 INTERNAL: failed to charge card: could not charge the card: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.15:50051: connect: connection refused"
2026-09-10T06:41:59.276489+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T06:41:59.276491+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T06:41:59.276492+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_45c62bb85445`:

```
<tool_result id="tr_45c62bb85445" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T04:06:45.583000+00:00..2026-09-10T07:08:49.114959+00:00" template="error-ratio" baseline="2026-09-10T01:04:42.051041+00:00..2026-09-10T04:06:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=729 mean=0.002313 min=0 max=0.1099 sd=0.01484
  baseline window: n=440 mean=0 min=0 max=0 sd=0
```

## Open threads for the next responder

The flag flip was never directly observed. Both change-history queries covered onset-forward only; re-run them with a window starting several hours earlier.

The callee's own logs were never read. Find the correct label value for productcatalogservice in Loki and confirm the flag from the emitting side.

Latency, CPU and memory for productcatalogservice were not returned. A resource contribution is unexcluded, not excluded.

Frontend's error ratio sitting at about a quarter of baseline while it demonstrably emits catalog INTERNAL errors is unexplained. It may be a traffic-mix or window-alignment artifact, or the catalog failures may touch only a fraction of routes. Worth resolving, because it is exactly the panel that would talk a responder out of investigating.

The 50051 connection-refused failure on the card-charge path was never attributed to a service.

Four of the seven services in the blast radius received no dispatch at all, and triage recorded one unmeasured edge crossed. Propagation to loadgenerator and to the untouched services is inferred, not measured.

> Evidence `tr_9eb4b888ea57`:

```
<tool_result id="tr_9eb4b888ea57" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T07:06:45.583000+00:00..2026-09-10T07:08:49.114959+00:00" radius="seed" hops="0">
no changes recorded for productcatalogservice over this window
</tool_result:tr_9eb4b888ea57>
```

> Evidence `tr_fb55115e9618`:

```
<tool_result id="tr_fb55115e9618" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T07:06:45.583000+00:00..2026-09-10T07:08:49.114959+00:00" radius="seed" hops="0">
no changes recorded for productcatalogservice over this window
</tool_result:tr_fb55115e9618>
```

> Evidence `tr_2f2afdbbe325`:

```
<tool_result id="tr_2f2afdbbe325" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-09-10T05:06:45.583000+00:00..2026-09-10T07:08:49.114959+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_2f2afdbbe325>
```

> Evidence `tr_45c62bb85445`:

```
<tool_result id="tr_45c62bb85445" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T04:06:45.583000+00:00..2026-09-10T07:08:49.114959+00:00" template="error-ratio" baseline="2026-09-10T01:04:42.051041+00:00..2026-09-10T04:06:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=729 mean=0.002313 min=0 max=0.1099 sd=0.01484
  baseline window: n=440 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_1ebf001ca2cc`:

```
<tool_result id="tr_1ebf001ca2cc" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T06:36:45.583000+00:00..2026-09-10T07:08:49.114959+00:00" template="error-ratio" baseline="2026-09-10T06:04:42.051041+00:00..2026-09-10T06:36:45.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=129 mean=0.01347 min=0 max=0.1081 sd=0.03237
  baseline window: n=129 mean=0.05372 min=0 max=0.3013 sd=0.1059
```

> Evidence `tr_43523bfab685`:

```
<tool_result id="tr_43523bfab685" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T06:36:45.583000+00:00..2026-09-10T07:08:49.114959+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T06:41:59.276453+00:00  Error: 13 INTERNAL: failed to charge card: could not charge the card: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.15:50051: connect: connection refused"
2026-09-10T06:41:59.276489+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T06:41:59.276491+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T06:41:59.276492+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

