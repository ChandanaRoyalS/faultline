# Checkout and cart failures traced to a cart backend that never came back

## What was visible first, and the first dead end

The page named frontend, loadgenerator and checkoutservice together; call that moment T0. Frontend's error ratio was elevated but partial, peaking near 38% and repeatedly returning to zero. checkoutservice looked similar, peaking around two-thirds of calls failing with a zero floor, though volume was low enough in some buckets that two of three calls failing would produce that ceiling. Both series were continuous, so neither service had lost telemetry.

That intermittency was the first thing to mislead. A bursty ratio reads like a load-dependent or flapping problem; in fact it was just an artifact of which requests touch the affected path.

Because checkoutservice alerted and showed the highest peak, its change history was pulled first. It came back empty — no rollout, no config edit, no flag flip near onset — which cleared two obvious mitigations at once. Caveat for the record: the interval actually returned covered about fifteen minutes around onset, not the ninety-minute lookback requested, so only the near-onset conclusion is supported.

> Evidence `tr_3a00c4f73082`:

```
<tool_result id="tr_3a00c4f73082" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T07:54:45.583000+00:00..2026-08-28T08:09:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.38 n=57
</tool_result:tr_3a00c4f73082>
```

> Evidence `tr_b9364622d8c5`:

```
<tool_result id="tr_b9364622d8c5" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T07:54:45.583000+00:00..2026-08-28T08:09:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=58
</tool_result:tr_b9364622d8c5>
```

> Evidence `tr_fd1169d59f64`:

```
<tool_result id="tr_fd1169d59f64" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-28T07:54:45.583000+00:00..2026-08-28T08:09:45.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_fd1169d59f64>
```

## Traces relocated the problem and eliminated three suspected edges

Sampling failing frontend traces was the turn. In every PlaceOrder trace the innermost erroring span was checkoutservice's client-side call to CartService/GetCart, nested under order preparation; PlaceOrder aborted there in two to four milliseconds with no unattributed time inside checkoutservice. The same edge broke frontend's direct GetCart and AddItem calls, one containing a connect span erroring after about three seconds. No server-side cart spans appeared anywhere — the tree simply stopped on the client side.

Two shapes coexisted: slow errors up to roughly three seconds and errors completing in well under a millisecond. That mix rules out a healthy-but-slow backend timing out. Product catalog, ad, recommendation and feature-flag spans were clean and fast in the same window, closing off any platform-wide theory.

Triage flagged four unmeasured edges. Payment, currency and accounting were eliminated not by measurement but by absence: PlaceOrder aborts before they are ever called and no spans naming them appear. The fourth edge was never identified or examined.

Cartservice's own metrics then returned nothing at all — no error numerator and, critically, no call denominator. This neither shows an error spike nor clears the service; a component that stopped emitting spans produces the identical empty result.

> Evidence `tr_a6b4957d27da`:

```
<tool_result id="tr_a6b4957d27da" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-28T07:54:45.583000+00:00..2026-08-28T08:09:45.583000+00:00">
service: frontend
200 spans
  4f0f748ce215e634 loadgenerator/HTTP GET 19.9ms
  4f0f748ce215e634 frontend/HTTP GET 18.4ms
  2005290cf4c49a2f frontend/HTTP GET 9.8ms
```

> Evidence `tr_1ad518231fb2`:

```
<tool_result id="tr_1ad518231fb2" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-28T07:54:45.583000+00:00..2026-08-28T08:09:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_1ad518231fb2>
```

## The cause, the fix class, and what is still open

cartservice logs held only routine cart operations, no errors or cache failures, continuing normally to within seconds of the end. The last retained line is a hosting-lifetime notice that the application began shutting down at about T-3m20s, followed by total silence for the remaining eight minutes — no requests, no startup from any replacement. The orderly notice rules out a crash or memory kill; the clean operations rule out a cache backend origin; the silence rules out network policy, mesh or frontend-side configuration.

The change history for cartservice held exactly one entry in the window: an automation-pushed image reference update onto a tag labelled as a hotfix, landing at the same moment as the shutdown. No config, environment or cache-connection change appears.

The artifact now referenced is not running or not serviceable. With no cart backend listening, frontend's direct calls and checkoutservice's client-side GetCart fail on the connection itself and PlaceOrder aborts before payment, currency or accounting. Everything upstream is collateral on that one edge. Fix class is rollback; confidence medium.

Still open: the prior image reference is recorded as absent, so what a rollback restores to is unestablished — confirm the target first. No pod or container evidence was collected, so whether the new image failed to pull, failed to start, or died before logging is unknown. The roughly three-minute-twenty gap between the shutdown and the first alerts is unexplained. Cart traffic and latency before the shutdown were never retrieved, so an earlier degradation that motivated the hotfix cannot be ruled in or out. Finally, whether the cart's own cache dependency is reachable for a restored instance is untested.

> Evidence `tr_8e77bd20f3da`:

```
<tool_result id="tr_8e77bd20f3da" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-28T07:54:45.583000+00:00..2026-08-28T08:09:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-28T07:54:48.455051+00:00  GetCartAsync called with userId=
2026-08-28T07:54:48.468141+00:00  GetCartAsync called with userId=
2026-08-28T07:54:48.549457+00:00  GetCartAsync called with userId=
2026-08-28T07:54:49.730826+00:00  AddItemAsync called with userId=bead1ab0-a2b5-11f1-ac74-5e36fd0150fc, productId=0PUK6V6EV0, quantity=3
```

> Evidence `tr_e408e150cb41`:

```
<tool_result id="tr_e408e150cb41" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-28T07:54:45.583000+00:00..2026-08-28T08:09:45.583000+00:00">
service: cartservice
1 changes
  2026-08-28T08:01:25.696707+00:00  platform-automation  image updated: image reference updated on cartservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-cartservice-hotfix.2
</tool_result:tr_e408e150cb41>
```

> Evidence `tr_1ad518231fb2`:

```
<tool_result id="tr_1ad518231fb2" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-28T07:54:45.583000+00:00..2026-08-28T08:09:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_1ad518231fb2>
```
