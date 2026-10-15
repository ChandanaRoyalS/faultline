# Checkout and frontend failures traced to a cart rollout that never came back up

## What the responder saw first

The page arrived from four services at once: frontend, frontend-proxy, checkout, and load-generator. Blast radius was recorded as thirteen services, severity critical, with frontend named as the entry point. That framing is misleading if you take it literally — frontend is where the symptom surfaced and where the alerting is richest, not where anything broke. Thirteen edges were crossed without measurement, so the reported radius is a graph walk, not a confirmed count of independently broken services.

The first useful observation is in frontend's own logs. Starting a little under a minute before the alert window closes (roughly T-1m to T+0), frontend emits repeated gRPC code 14 UNAVAILABLE errors saying no connection could be established to a peer at 172.18.0.24 port 7070, including a host-unreachable network condition. Separately, about four seconds before the alert, a checkout-path call fails with gRPC code 13 INTERNAL while fetching a user cart; its underlying cause is an UNAVAILABLE from the name resolver, which returned zero addresses for the target.

Zero addresses is the line that matters. A partially failing deployment produces some endpoints and some failures. Zero resolved endpoints means nothing was registered as Ready behind that name.

> Evidence `tr_f72635268a0b`:

```
<tool_result id="tr_f72635268a0b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T05:46:46.664000+00:00..2026-10-14T05:46:46.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-07T05:51:53.919904+00:00  Error: 13 INTERNAL: failed to charge card: could not charge the card: rpc error: code = Unavailable desc = error reading from server: EOF
2026-10-07T05:51:53.919960+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-07T05:51:53.919970+00:00      at new Promise (<anonymous>) {
2026-10-07T05:51:53.919971+00:00    code: 13,
```

## Following the symptom upstream

Frontend's change history was checked next, on the assumption that the alerting service had shipped something. It had not. Every one of the ten recorded changes across the seven-day window is the same environment variable, CART_ADDR, being set to a non-default cart address and then reverted, always by platform-automation. No code deploy, no image rollout, no flag change appears anywhere in the window.

The closest set/revert pair ran for about nine minutes and was reverted roughly an hour before onset, so frontend was running with the default cart address when the incident began. The same set/revert pattern repeats five times over three days, which makes it routine background activity rather than an anomaly tied to this onset. It is a tempting shape — automation touching the exact variable that points at the failing dependency — and it cost time. It is not the cause.

> Evidence `tr_e3b00488f813`:

```
<tool_result id="tr_e3b00488f813" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T05:46:46.664000+00:00..2026-10-14T05:48:51.196662+00:00" radius="seed" hops="0">
service: frontend
10 changes, ranked by suspicion
  #1  1.1h before onset  2026-10-14T04:43:01.757364+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
      CART_ADDR=cart:7071  ->  None
  #2  1.2h before onset  2026-10-14T04:34:34.057124+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
```

## Cart: the change and the quiet that followed

Cart's change history put a rollout about three minutes before onset (T-3m): platform-automation updated cart's image reference to the 2.2.0-cart-hotfix.2 tag. Cart's own logs line up with that. Up to essentially that same moment the service is emitting routine info-level cart store operations — reads, item additions, cart emptying — with no error or warning entries at all. Then it logs an orderly, staged application shutdown: hosting lifetime announces shutdown, flag lifecycle manager stops, feature provider stops. The log window closes there. No startup message, no host-build line, no listening or bind entry afterwards.

Read together: the old pod was drained for the rollout and the replacement never came up serving. Three minutes later the callers notice. Frontend, frontend-proxy, checkout and load-generator alerted in caller order because the dependency underneath them had no endpoints left.

> Evidence `tr_da7e0bd1d132`:

```
<tool_result id="tr_da7e0bd1d132" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T05:46:46.664000+00:00..2026-10-14T05:48:51.196662+00:00" radius="candidate_cause" hops="1">
service: cart
21 changes, ranked by suspicion
  #1  3m before onset  2026-10-14T05:43:37.162806+00:00  platform-automation  image updated: image reference updated on cart
      None  ->  ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2
  #2  1.4h before onset  2026-10-14T04:20:44.828821+00:00  platform-automation  image reverted: image reference reverted on cart
```

> Evidence `tr_f8b93e0fa29a`:

```
<tool_result id="tr_f8b93e0fa29a" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T05:46:46.664000+00:00..2026-10-14T05:46:46.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-07T05:47:04.324693+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T05:47:04.324777+00:00        GetCartAsync called with userId=
2026-10-07T05:47:07.530447+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T05:47:07.530467+00:00        AddItemAsync called with userId=882fecca-c212-11f1-9fe0-eedf78b04444, productId=2ZYFJ3GM2N, quantity=3
```

## Dead ends worth keeping

Several plausible stories were examined and discarded, and a responder reading this later should not re-run them.

Cart did not crash or get killed. The termination is a graceful, staged lifecycle shutdown with subsystems stopping in order; an abrupt kill would truncate mid-request with no such notices, and there are no memory-pressure or unhandled-exception entries.

Cart was not degraded before it stopped. The entries immediately preceding shutdown are successful cart store operations at info level — no timeouts, no retries, no store connection errors.

The downstream was not slow. The frontend errors say no connection was established at all, with a host-unreachable condition — not deadline exceeded. A reachable-but-overloaded peer does not produce these.

Nothing was rejected at the application layer. Both error families resolve to transport-level causes, so no RPC reached a service handler.

The failure is not inside frontend's own code. The stack frames are generic promise wrappers around gRPC client calls, and every detail string attributes the failure outward.

The older frontend errors are a red herring. At the far end of the seven-day window there is a distinct family: code 13 INTERNAL card-charge failures caused by an UNAVAILABLE payment backend dropping the connection, with a different peer address and port. Different problem, days earlier.

A traffic-shaping sidecar had been attached to and detached from cart's network namespace with a fixed 300ms delay on eth0 — but the last detach was roughly 124 hours before onset and no later attachment is recorded. It was not in place.

No scale-down, replica-count, or resource-limit change to cart exists in the window. No Service or Endpoint object change exists either, so a broken selector or port is not on the table. Every recorded change on both services is attributed to platform-automation; no human actor appears anywhere.

> Evidence `tr_f8b93e0fa29a`:

```
<tool_result id="tr_f8b93e0fa29a" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T05:46:46.664000+00:00..2026-10-14T05:46:46.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-07T05:47:04.324693+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T05:47:04.324777+00:00        GetCartAsync called with userId=
2026-10-07T05:47:07.530447+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T05:47:07.530467+00:00        AddItemAsync called with userId=882fecca-c212-11f1-9fe0-eedf78b04444, productId=2ZYFJ3GM2N, quantity=3
```

> Evidence `tr_f72635268a0b`:

```
<tool_result id="tr_f72635268a0b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T05:46:46.664000+00:00..2026-10-14T05:46:46.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-07T05:51:53.919904+00:00  Error: 13 INTERNAL: failed to charge card: could not charge the card: rpc error: code = Unavailable desc = error reading from server: EOF
2026-10-07T05:51:53.919960+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-07T05:51:53.919970+00:00      at new Promise (<anonymous>) {
2026-10-07T05:51:53.919971+00:00    code: 13,
```

> Evidence `tr_da7e0bd1d132`:

```
<tool_result id="tr_da7e0bd1d132" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T05:46:46.664000+00:00..2026-10-14T05:48:51.196662+00:00" radius="candidate_cause" hops="1">
service: cart
21 changes, ranked by suspicion
  #1  3m before onset  2026-10-14T05:43:37.162806+00:00  platform-automation  image updated: image reference updated on cart
      None  ->  ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2
  #2  1.4h before onset  2026-10-14T04:20:44.828821+00:00  platform-automation  image reverted: image reference reverted on cart
```

## The metrics gap

No metrics were obtained at any point. Three separate attempts — two against frontend, one against cart — all failed with HTTP 400 Bad Request. The same error-ratio template was used each time and was rejected before evaluation.

This needs stating plainly for whoever reads this next: those empty results are not negatives. They do not show that frontend's error ratio was flat, they do not show that cart emitted no metrics, and they do not show that cart's serving instances dropped to zero. A 400 is a live server parsing and rejecting a request, so the backend was up and reachable; retention gaps and scrape outages would have returned empty-but-successful responses instead. The failure is in the query template itself, and fixing it is a real action item independent of this incident. Because of it, onset timing, error volume, and cart replica count rest entirely on logs with no independent confirmation.

> Evidence `tr_8a7135c95c50`:

```
<tool_result id="tr_8a7135c95c50" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-07T05:46:46.664000+00:00..2026-10-14T05:46:46.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-30T05:46:46.664000+00:00..2026-10-07T05:46:46.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_8a7135c95c50>
```

> Evidence `tr_b0ab1469979e`:

```
<tool_result id="tr_b0ab1469979e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-07T05:46:46.664000+00:00..2026-10-14T05:46:46.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-30T05:46:46.664000+00:00..2026-10-07T05:46:46.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_b0ab1469979e>
```

> Evidence `tr_808bb5045ceb`:

```
<tool_result id="tr_808bb5045ceb" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-07T05:46:46.664000+00:00..2026-10-14T05:46:46.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-30T05:46:46.664000+00:00..2026-10-07T05:46:46.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_808bb5045ceb>
```

## Conclusion and confidence

The rollout at T-3m drained cart's serving pod and the replacement artifact never reached Ready, leaving zero endpoints behind the cart name. Callers on the cart path failed from T+0 onward. Fix class is rollback: revert cart's image reference to the prior tag.

Confidence is medium, and the reasons are specific. Why the replacement pods never became Ready is unproven — image pull failure, crash on start, failed readiness probe, and admission or scheduling rejection are all still open, because no cart startup or container-runtime evidence was collected. The same hotfix tag had been applied and reverted successfully several times in the preceding hours and days, so a deterministic bad image is not established; a flaky rollout or an environment-dependent startup failure fits that history just as well. The peer at 172.18.0.24:7070 is never named as cart by any evidence — the identification rests on the port number and the cart-fetch error in the checkout path, not on a confirmed endpoint mapping. Nine of the thirteen affected services were never examined, so whether they all fail through the cart path or some have an independent cause is untested. And cart's log window closes at the shutdown, so whether it recovered on its own before the investigation began is unknown.

> Evidence `tr_da7e0bd1d132`:

```
<tool_result id="tr_da7e0bd1d132" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T05:46:46.664000+00:00..2026-10-14T05:48:51.196662+00:00" radius="candidate_cause" hops="1">
service: cart
21 changes, ranked by suspicion
  #1  3m before onset  2026-10-14T05:43:37.162806+00:00  platform-automation  image updated: image reference updated on cart
      None  ->  ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2
  #2  1.4h before onset  2026-10-14T04:20:44.828821+00:00  platform-automation  image reverted: image reference reverted on cart
```

> Evidence `tr_f8b93e0fa29a`:

```
<tool_result id="tr_f8b93e0fa29a" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T05:46:46.664000+00:00..2026-10-14T05:46:46.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-07T05:47:04.324693+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T05:47:04.324777+00:00        GetCartAsync called with userId=
2026-10-07T05:47:07.530447+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T05:47:07.530467+00:00        AddItemAsync called with userId=882fecca-c212-11f1-9fe0-eedf78b04444, productId=2ZYFJ3GM2N, quantity=3
```

> Evidence `tr_f72635268a0b`:

```
<tool_result id="tr_f72635268a0b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T05:46:46.664000+00:00..2026-10-14T05:46:46.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-07T05:51:53.919904+00:00  Error: 13 INTERNAL: failed to charge card: could not charge the card: rpc error: code = Unavailable desc = error reading from server: EOF
2026-10-07T05:51:53.919960+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-07T05:51:53.919970+00:00      at new Promise (<anonymous>) {
2026-10-07T05:51:53.919971+00:00    code: 13,
```

