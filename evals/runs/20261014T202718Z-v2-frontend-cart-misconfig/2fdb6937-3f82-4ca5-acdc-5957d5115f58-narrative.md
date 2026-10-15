# Frontend Cart Address Override Left In Place — Connection Refused Across Checkout Path

## What we saw, and the first dead end

Four services alerted together: frontend, frontend-proxy, load-generator and checkout. Blast radius was thirteen services, severity critical, origin frontend. The alert set is misleading in a specific way — every one of those four is downstream or adjacent on frontend's request path, so all four were reporting symptom, not cause. Nothing in the initial page named the service that actually appeared in the failing connection.

Before touching logs we tried to baseline frontend's error ratio against the preceding week. The query never ran: the metrics backend returned a 400 Bad Request, meaning it parsed the request and rejected it as malformed. The same query shape re-pointed at cart failed identically. This cost time twice — once when issued, and again when the empty-looking result was briefly mistaken for a flat series. It is not. A rejected request says nothing about the underlying data, so we did not conclude that frontend errors were flat, that cart was clean, or that the metrics stack was down (a dead backend gives a timeout or 5xx, not a 400). Consequence for the whole record: no measured onset time, no per-route or per-dependency error breakdown, no restart counts. Everything below rests on logs and change history. If this recurs, fix the query template first.

> Evidence `tr_30019e988363`:

```
<tool_result id="tr_30019e988363" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-07T20:30:31.664000+00:00..2026-10-14T20:30:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-30T20:30:31.664000+00:00..2026-10-07T20:30:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_30019e988363>
```

> Evidence `tr_a8a6ef95d728`:

```
<tool_result id="tr_a8a6ef95d728" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-07T20:30:31.664000+00:00..2026-10-14T20:30:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-30T20:30:31.664000+00:00..2026-10-07T20:30:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_a8a6ef95d728>
```

## The signal that mattered, and the change behind it

Frontend's logs carried a high-rate repeating gRPC status 14 UNAVAILABLE whose detail is the whole investigation: a refused TCP connection to 172.18.0.24:7071, with a last-error timestamp trailing emission by a minute or two — a tight retry loop. Connection refused is specific. The name resolved, the packet reached a host, and nothing was bound to that port. That kills three stories at once: not DNS or discovery (the resolved IP is in the error), not saturation (overload yields deadline-exceeded, not instant rejection), not a frontend code bug (every line describes a client-side call to something else).

Frontend's change history holds fifteen entries, all from the same automated actor, all the same variable: CART_ADDR set to cart:7071 then unset. No deploys, no flag flips, no human edits. The pair repeated seven times (≈65h, 62h, 42.9h, 42.2h, 15.9h, 12.1h, 4.7h before onset), six of them reverted within eight or nine minutes and none causing an incident. We briefly treated "CART_ADDR is set" as the answer and had to back off — the setting alone is not sufficient. The seventh landed three minutes before onset and was never reverted. The port in the override is the port in the refusal.

> Evidence `tr_98a3591b5fb7`:

```
<tool_result id="tr_98a3591b5fb7" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T20:30:31.664000+00:00..2026-10-14T20:30:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-07T23:48:48.880349+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-10-07T23:48:48.881529+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-07T23:48:48.881546+00:00      at new Promise (<anonymous>) {
2026-10-07T23:48:48.881553+00:00    code: 14,
```

> Evidence `tr_7698e78df7dd`:

```
<tool_result id="tr_7698e78df7dd" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T20:30:31.664000+00:00..2026-10-14T20:32:23.558408+00:00" radius="seed" hops="0">
service: frontend
15 changes, ranked by suspicion
  #1  3m before onset  2026-10-14T20:27:28.512969+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
      None  ->  CART_ADDR=cart:7071
  #2  4.6h before onset  2026-10-14T15:54:48.298326+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
```

## Ruling out cart

Cart was the obvious suspect and is not it. Its logs are exclusively info-level cart-store reads and item-adds against a Valkey-backed store — no errors, warnings or stack traces — serving distinct per-user requests seconds apart up to about two seconds before the window closed. That rules out crash-looping, restarts, a pre-ready state, being hard-down, and an unreachable backing store. A service refusing connections does not simultaneously log a dense stream of served calls.

Cart's change history adds the rest: twenty-six automated entries in two families only — image-reference flips to and from one hotfix tag, and attach/detach of a traffic-shaping sidecar (300ms eth0 delay). Neither touches ports, listeners or service definitions. The hotfix was reverted off eleven hours before onset; every shaping attach is matched by a removal, the last ~139h prior. The nearest change of any kind to cart precedes onset by eleven hours, so onset is not change-coincident here. The theory that cart quietly moved its listener off 7071 has no support.

> Evidence `tr_f385dc3c5114`:

```
<tool_result id="tr_f385dc3c5114" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T20:30:31.664000+00:00..2026-10-14T20:30:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-07T20:30:32.397721+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T20:30:32.397749+00:00        GetCartAsync called with userId=
2026-10-07T20:30:33.063334+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T20:30:33.063377+00:00        AddItemAsync called with userId=f1f18814-c28d-11f1-9fe0-eedf78b04444, productId=6E92ZMYYFZ, quantity=2
```

> Evidence `tr_c7758f64d9bc`:

```
<tool_result id="tr_c7758f64d9bc" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T20:30:31.664000+00:00..2026-10-14T20:32:23.558408+00:00" radius="candidate_cause" hops="1">
service: cart
26 changes, ranked by suspicion
  #1  11.0h before onset  2026-10-14T09:29:44.698951+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  11.1h before onset  2026-10-14T09:23:04.139532+00:00  platform-automation  image updated: image reference updated on cart
```

## The second error we did not solve

Interleaved in the same seconds is a different failure: gRPC status 13 INTERNAL from a shipping-quote path, reporting an HTTP POST to the email service returning 400 instead of 200. The stack frames differ from the UNAVAILABLE lines, consistent with two unrelated call paths failing concurrently. No connectivity problem produces a 400.

We chased it and came back empty. Email's history is sixteen automated entries, all the same image reference flapping between unset and a demo 2.2.0-quote image, clustered ~106–108h and ~87–88h before onset. The most recent is a revert, so the quote image was not running. There are no schema, migration, validation or config entries for email at all. Not a recent deploy, not a schema change, not tightened validation, not that image, not a human. Unexplained; possibly a separate failure needing its own fix.

> Evidence `tr_98a3591b5fb7`:

```
<tool_result id="tr_98a3591b5fb7" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T20:30:31.664000+00:00..2026-10-14T20:30:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-07T23:48:48.880349+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-10-07T23:48:48.881529+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-07T23:48:48.881546+00:00      at new Promise (<anonymous>) {
2026-10-07T23:48:48.881553+00:00    code: 14,
```

> Evidence `tr_cf6bd139479b`:

```
<tool_result id="tr_cf6bd139479b" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T20:30:31.664000+00:00..2026-10-14T20:32:23.558408+00:00" radius="candidate_cause" hops="1">
service: email
16 changes, ranked by suspicion
  #1  87.2h before onset  2026-10-11T05:19:38.994874+00:00  platform-automation  image reverted: image reference reverted on email
      ghcr.io/open-telemetry/demo:2.2.0-quote  ->  None
  #2  87.4h before onset  2026-10-11T05:05:47.541407+00:00  platform-automation  image updated: image reference updated on email
```

## Conclusion, and what stays open

Three minutes before onset, platform-automation set CART_ADDR=cart:7071 on frontend and, unlike six identical prior sets, never reverted it. Frontend dialled that address and was refused at the transport layer: host reachable, no listener bound. Cart was healthy throughout with no port or listener change in its history. The wrong address value is itself the mechanism, and failures propagated to frontend-proxy, load-generator and checkout. Confidence high. Fix class: revert the configuration, as the six prior cycles did.

One caveat on prior history: UNAVAILABLE-family errors also appear at the oldest retained edge of the window, but with a connection-dropped detail rather than refused — a different transport outcome. Treat it as background instability, not an earlier instance of this.

Open: cart's actual listening port was never directly observed — no bind line in its logs and no service definition read, so the inference rests on the refusal plus cart's health. And there are no metrics for either service; both baselines were rejected, leaving error-ratio onset and restart counts unmeasured across thirteen crossed edges.

> Evidence `tr_7698e78df7dd`:

```
<tool_result id="tr_7698e78df7dd" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T20:30:31.664000+00:00..2026-10-14T20:32:23.558408+00:00" radius="seed" hops="0">
service: frontend
15 changes, ranked by suspicion
  #1  3m before onset  2026-10-14T20:27:28.512969+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
      None  ->  CART_ADDR=cart:7071
  #2  4.6h before onset  2026-10-14T15:54:48.298326+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
```

> Evidence `tr_98a3591b5fb7`:

```
<tool_result id="tr_98a3591b5fb7" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T20:30:31.664000+00:00..2026-10-14T20:30:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-07T23:48:48.880349+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-10-07T23:48:48.881529+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-07T23:48:48.881546+00:00      at new Promise (<anonymous>) {
2026-10-07T23:48:48.881553+00:00    code: 14,
```

> Evidence `tr_f385dc3c5114`:

```
<tool_result id="tr_f385dc3c5114" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T20:30:31.664000+00:00..2026-10-14T20:30:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-07T20:30:32.397721+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T20:30:32.397749+00:00        GetCartAsync called with userId=
2026-10-07T20:30:33.063334+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-07T20:30:33.063377+00:00        AddItemAsync called with userId=f1f18814-c28d-11f1-9fe0-eedf78b04444, productId=6E92ZMYYFZ, quantity=2
```

