# Frontend errors traced to unreachable shipping endpoint, with a second unexplained resolution failure

## What the responder saw first

The page came from two places at once: frontend and loadgenerator. Blast radius was drawn at seven services and the severity was set critical, so the initial expectation walking in was a broad customer-facing outage originating at the edge.

That expectation did not survive the first look at frontend's own logs. Every error line captured in the window is a gRPC client status produced on an outbound call, with the stack confined to the Node grpc-js client and interceptor path. Nothing shows frontend's own handlers throwing. Frontend is a messenger here, not a source.

The earliest error in the window, at roughly T+0, is a status 13 wrapping a transport dial failure to 172.18.0.7 on port 50050 — the shipping-quote backend. The name had already resolved to a concrete address; the connection was refused at TCP. That is the signature of a process that is not listening: down, not started, or not bound.

> Evidence `tr_bcae65308ea6`:

```
<tool_result id="tr_bcae65308ea6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T00:00:15.583000+00:00..2026-09-10T00:32:16.401788+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T00:00:16.237984+00:00  Error: 13 INTERNAL: shipping quote failure: failed to get shipping quote: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.7:50050: connect: connection refused"
2026-09-10T00:00:16.238002+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T00:00:16.238004+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T00:00:16.238004+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## The second symptom, later in the window

Near T+32m the dominant error changes character. Instead of a refused connection to an IP, frontend emits status 14 with details naming a DNS name resolution failure for adservice on port 9555, repeated several times inside a single second.

This matters because it is a different mechanism at a different layer against a different dependency. The shipping failure proves resolution worked and the listener was absent. The adservice failure proves resolution itself did not complete. A responder tempted to collapse both into one story should resist: nothing gathered here connects them. They may share an upstream cause in the node, the network namespace, or the service-discovery plane, or they may be unrelated. No dispatch tested that, and one edge in the graph was crossed without measurement.

> Evidence `tr_bcae65308ea6`:

```
<tool_result id="tr_bcae65308ea6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T00:00:15.583000+00:00..2026-09-10T00:32:16.401788+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T00:00:16.237984+00:00  Error: 13 INTERNAL: shipping quote failure: failed to get shipping quote: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.7:50050: connect: connection refused"
2026-09-10T00:00:16.238002+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T00:00:16.238004+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T00:00:16.238004+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Things ruled out at the frontend

Several plausible readings were closed off by the same log evidence. This was not an authorization, quota, or bad-request rejection — the statuses are 13 and 14, not the rejection codes, and upstreams were not answering at all rather than refusing work. It was not latency saturation with deadlines expiring; both failure modes occur before a request is ever served. It was not a TLS or handshake problem; the calls died at dial and resolve, before any handshake would begin. And it was not purely a discovery problem from the outset, because the first failure resolved cleanly and then found nobody home.

> Evidence `tr_bcae65308ea6`:

```
<tool_result id="tr_bcae65308ea6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T00:00:15.583000+00:00..2026-09-10T00:32:16.401788+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T00:00:16.237984+00:00  Error: 13 INTERNAL: shipping quote failure: failed to get shipping quote: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.7:50050: connect: connection refused"
2026-09-10T00:00:16.238002+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T00:00:16.238004+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T00:00:16.238004+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## The metric that looked useful and was not

A baseline comparison on frontend's aggregate error ratio was pulled early, hoping to timestamp onset. It was a dead end worth recording.

The ratio moved from about 1.8% in the preceding half hour to about 2.6% in the window — a factor of roughly 1.46, peaks under 10%, and the comparison classified it as no sustained departure from baseline. Two things follow. First, this rules out a service-wide outage: a dependency failing on the common request path would have driven that number far higher, so whatever is broken serves a minority of traffic. That is consistent with shipping quotes and ads. Second, the series is useless as an onset marker; the aggregate dilutes exactly the small-volume routes that were failing.

There is also a shape problem with how the query was framed. It aggregated only by service name, with no per-dependency or per-route breakdown and no latency term, so the question that actually mattered — which dependency's error curve tracks onset — was never answerable from it. The window also ended only about two minutes after onset while using a two-minute rate window, meaning at most one or two samples reflected post-onset behaviour. The absence of a visible step there carries almost no weight.

> Evidence `tr_740317c61dd9`:

```
<tool_result id="tr_740317c61dd9" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T00:00:15.583000+00:00..2026-09-10T00:32:16.401788+00:00" template="error-ratio" baseline="2026-09-09T23:28:14.764212+00:00..2026-09-10T00:00:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=129 mean=0.02642 min=0 max=0.0956 sd=0.02936
  baseline window: n=129 mean=0.01805 min=0 max=0.06186 sd=0.02313
```

## The change hunt, which found nothing relevant

Most of the investigative budget went into change history, and all of it came back empty of anything that explains the incident.

Frontend: no records at all across the queried window — no deploys, no config edits, no flag flips. The query ran at seed scope with zero hops, so it speaks only to frontend and not to its dependencies or shared infrastructure. Checkoutservice: likewise empty, and quiet for the full day after onset too, which incidentally means no remediation was applied mid-incident either. Note a framing defect worth remembering: that window began at the onset moment and ran forward roughly 24 hours, so it does not actually cover the pre-incident period the question was asking about.

Productcatalogservice: exactly two entries, both from platform automation, both attaching and then detaching a traffic-shaping container on the service's network namespace. It added a fixed egress delay for about eight and a half minutes and the setting was returned to unset on removal — roughly 18.4 hours before onset. Cartservice: 26 entries, all from the same automated actor, all in matched apply/revert pairs on a four-to-five-hour cadence — image reference, a Redis address variable, and a shaping sidecar. Every pair closed. The last mutation before onset was a revert about 1.9 hours prior, leaving a clean gap and nothing dangling.

So: no human touched anything, nothing was left applied, and the nearest mutation of any kind sits nearly two hours clear of onset. The change surface is quiet enough that the rest of the investigation can proceed against a static configuration.

> Evidence `tr_e23a4a5dfbd5`:

```
<tool_result id="tr_e23a4a5dfbd5" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T00:30:15.583000+00:00..2026-09-10T00:32:16.401788+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_e23a4a5dfbd5>
```

> Evidence `tr_2321fe80a532`:

```
<tool_result id="tr_2321fe80a532" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T00:30:15.583000+00:00..2026-09-10T00:32:16.401788+00:00" radius="candidate_cause" hops="1">
no changes recorded for checkoutservice over this window
</tool_result:tr_2321fe80a532>
```

> Evidence `tr_665283141e69`:

```
<tool_result id="tr_665283141e69" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T00:30:15.583000+00:00..2026-09-10T00:32:16.401788+00:00" radius="candidate_cause" hops="1">
service: productcatalogservice
2 changes, ranked by suspicion
  #1  18.4h before onset  2026-09-09T06:09:03.403533+00:00  platform-automation  container removed: traffic-shaping container removed from product-catalog-service's network namespace
      eth0 delay=300ms jitter=0ms  ->  None
  #2  18.5h before onset  2026-09-09T06:00:32.130376+00:00  platform-automation  container created: traffic-shaping container attached to product-catalog-service's network namespace
```

> Evidence `tr_ca3b26de3bf8`:

```
<tool_result id="tr_ca3b26de3bf8" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T00:30:15.583000+00:00..2026-09-10T00:32:16.401788+00:00" radius="candidate_cause" hops="1">
service: cartservice
26 changes, ranked by suspicion
  #1  1.9h before onset  2026-09-09T22:37:51.973364+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  2.0h before onset  2026-09-09T22:29:53.992613+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

## Where it landed

The best-supported reading is that the shipping service was unavailable at its listening endpoint, and frontend's errors are the faithful echo of that. Confidence is low. The likely remediation class is a restart of the shipping backend, but that is inference from the refused-connection signature, not from anything observed on the service itself.

The class of failure is deliberately left unstated because it was never established.

> Evidence `tr_bcae65308ea6`:

```
<tool_result id="tr_bcae65308ea6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T00:00:15.583000+00:00..2026-09-10T00:32:16.401788+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T00:00:16.237984+00:00  Error: 13 INTERNAL: shipping quote failure: failed to get shipping quote: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.7:50050: connect: connection refused"
2026-09-10T00:00:16.238002+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T00:00:16.238004+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T00:00:16.238004+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Open, and where the next responder should start

The single largest gap: no dispatch ever examined shippingservice. Whether it crashed, was killed for memory, is looping, or was never scheduled is entirely unknown — and that distinction is what determines the actual failure class and the right fix. Start there.

Related: shippingservice's own change history was never queried. The change budget was spent on four services that turned out to have nothing relevant, and the one service actually implicated at onset was never asked. The trigger could still be sitting in that log.

The adservice resolution failures remain unexplained. They could be a second independent problem, a shared control-plane or discovery issue, or a downstream consequence. No infrastructure-level dispatch was made, so the hypothesis that one upstream cause — a node, a network namespace, the discovery plane — produces both symptoms was never tested. Given that an unmeasured edge was crossed during triage, treat the two-cause and one-cause readings as equally live.

> Evidence `tr_bcae65308ea6`:

```
<tool_result id="tr_bcae65308ea6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T00:00:15.583000+00:00..2026-09-10T00:32:16.401788+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T00:00:16.237984+00:00  Error: 13 INTERNAL: shipping quote failure: failed to get shipping quote: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.7:50050: connect: connection refused"
2026-09-10T00:00:16.238002+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T00:00:16.238004+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T00:00:16.238004+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_e23a4a5dfbd5`:

```
<tool_result id="tr_e23a4a5dfbd5" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T00:30:15.583000+00:00..2026-09-10T00:32:16.401788+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_e23a4a5dfbd5>
```

